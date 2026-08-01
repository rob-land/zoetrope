"""zoetrope entrypoint.

  zoetrope run [--mode auto|preview|glasses] [--tracker auto|xrdriver|hidraw|stub]
                [--media DIR] [--sway] [--monitor NAME]
  zoetrope watch     # daemon: launch/stop the shell as glasses are plugged/unplugged
  zoetrope info      # print detected glasses / display, then exit

Run without glasses:  zoetrope run --mode preview --sway
"""
from __future__ import annotations

import argparse
import os
import sys
import time

from . import detect, display as display_mod
from .config import PROFILES, GlassesProfile
from . import stereo as stereo_mod
from .stereo import HeadPose, eye_matrices, mono_matrices


def _resolve_profile(usb, disp) -> GlassesProfile:
    if disp is not None and disp.profile is not None and disp.profile.usb_pids:
        return disp.profile
    if usb is not None and usb.profile is not None and usb.profile.usb_pids:
        return usb.profile
    return PROFILES["one_pro"]  # sensible default / dev target


def cmd_info(args) -> int:
    usb = detect.find_glasses()
    disp = display_mod.find_display()
    print("USB glasses :", f"{usb.profile.name} (pid {usb.pid:#06x}) at {usb.sysfs_path}"
          if usb else "none found (VID 0x3318)")
    print("DP output   :", f"{disp.connector} -> {disp.output_name} "
          f"[{disp.profile.name if disp.profile else '?'}]" if disp else "none (EDID MRG/NRL)")
    prof = _resolve_profile(usb, disp)
    print("Profile     :", prof.name,
          f"{prof.sbs_width}x{prof.sbs_height}@{prof.refresh_hz} SBS, "
          f"fov_h {prof.fov_h_deg}, ipd {prof.ipd_m}")
    return 0


def cmd_run(args) -> int:
    from .window import (Window, WindowConfig, EV_QUIT, EV_RECENTER,
                         EV_PREV, EV_NEXT, EV_UP, EV_DOWN, EV_ACTIVATE, EV_BACK)
    from .renderer import StereoRenderer
    from .shell import Shell
    from . import tracking

    usb = detect.find_glasses()
    disp = display_mod.find_display()
    profile = _resolve_profile(usb, disp)

    mode = args.mode
    if mode == "auto":
        mode = "glasses" if disp is not None else "preview"

    # Decide stereo (SBS) vs mono. The glasses only advertise the 3840x1080 SBS mode
    # once switched into 3D (a proprietary command / the glasses' on-board toggle);
    # until then they're a 2D 1920x1080 monitor and we must render mono.
    if args.stereo == "sbs":
        stereo = True
    elif args.stereo == "mono":
        stereo = False
    else:  # auto
        stereo = bool(disp is not None and display_mod.sbs_available(disp, profile))

    if mode == "glasses" and disp is not None:
        modes = ", ".join(display_mod.output_modes(disp.connector)) or "?"
        print(f"[display] {disp.profile.name if disp.profile else 'glasses'} on "
              f"{disp.output_name}; modes: {modes}")
        if stereo:
            display_mod.set_sbs_mode(disp, profile)  # best-effort on wlroots/X11
            print(f"[display] rendering STEREO (side-by-side "
                  f"{profile.sbs_width}x{profile.sbs_height})")
        else:
            print("[display] rendering MONO (2D). No 3840x1080 SBS mode is exposed.")
            print("          -> To get real 3D, switch the glasses into their 3D / "
                  "Side-by-Side display mode (on-board button/menu); zoetrope will")
            print("          -> auto-detect it. Host-side mode-setting isn't available on "
                  "GNOME/Mutter Wayland.")

    win = Window(WindowConfig(
        mode=mode,
        monitor_name=args.monitor or (disp.output_name if disp else None),
        width=1920, height=540, title="zoetrope",
    ))
    ctx = win.make_gl_context()
    renderer = StereoRenderer(ctx)
    tracker = tracking.open_tracker(
        args.tracker, vid=usb.vid if usb else None, sway=args.sway)
    from .providers import ProviderHub
    shell = Shell(ctx, args.media, win.get_proc_address,
                  library_dir=args.library, hub=ProviderHub())
    from .controller import open_controller
    controller = open_controller(args.controller)
    remote = None
    if args.remote:
        from .remote import RemoteServer
        remote = RemoteServer(port=args.remote)
        print(f"[remote] phone touchpad at {remote.url()}  (LAN-open, unauthenticated)")

    print(f"[run] mode={mode} profile={profile.name} tracker={type(tracker).__name__}"
          f" controller={'daydream' if controller else 'none'}")
    print("      keys: arrows=select  enter=open  backspace=back  R=recenter  esc=quit")
    print("      in-app: left/right=smaller/bigger  up/down=push/pull")
    if controller:
        print("      daydream: point=select  click=open  app=back  home=recenter"
              "  h-swipe/vol=prev/next|size  v-swipe=push/pull")

    last = time.monotonic()
    try:
        while True:
            now = time.monotonic()
            dt = now - last
            last = now
            quit_ = False
            for ev in win.poll():
                if ev == EV_QUIT:
                    quit_ = True
                elif ev == EV_RECENTER:
                    tracker.recenter()
                    if controller:
                        controller.recenter()
                elif ev == EV_PREV:
                    shell.on_prev()
                elif ev == EV_NEXT:
                    shell.on_next()
                elif ev == EV_UP:
                    shell.on_farther()
                elif ev == EV_DOWN:
                    shell.on_closer()
                elif ev == EV_ACTIVATE:
                    shell.on_activate()
                elif ev == EV_BACK:
                    shell.on_back()
            if quit_:
                break

            cursor = None
            if controller:
                for cev in controller.poll_events():
                    if cev == "activate":
                        shell.on_activate()
                    elif cev == "back":
                        shell.on_back()
                    elif cev == "recenter":
                        tracker.recenter()
                        controller.recenter()
                    elif cev == "prev":
                        shell.on_prev()
                    elif cev == "next":
                        shell.on_next()
                    elif cev == "up":
                        shell.on_farther()
                    elif cev == "down":
                        shell.on_closer()
                cursor = controller.pointer()
                if cursor is not None:
                    shell.on_pointer(cursor[0])

            if remote:
                for rev in remote.poll_events():
                    {"prev": shell.on_prev, "next": shell.on_next,
                     "up": shell.on_farther, "down": shell.on_closer,
                     "activate": shell.on_activate, "back": shell.on_back,
                     "recenter": tracker.recenter}[rev]()
                rtext = remote.poll_text()
                if rtext:
                    shell.on_text(rtext)

            typed = win.poll_chars()
            if typed:
                shell.on_text(typed)
            win.text_mode = shell.wants_text()

            # 3DoF trackers give orientation only; the neck model
            # synthesizes the few cm of eye translation a real head has.
            pose = stereo_mod.apply_neck_model(
                HeadPose(orientation=tracker.get_orientation()))
            shell.update(dt, pose)

            fb_w, fb_h = win.framebuffer_size()
            if fb_w == 0 or fb_h == 0:      # Wayland can report 0x0 before first configure
                continue
            if stereo:
                eyes = eye_matrices(pose, fb_w, fb_h, profile.fov_h_deg, profile.ipd_m)
            else:
                eyes = mono_matrices(pose, fb_w, fb_h, profile.fov_h_deg)
            renderer.render((fb_w, fb_h), shell.panels_models(), eyes,
                            shell.floor_model(), shell.selected_id(), cursor=cursor,
                            void_theater=shell.wants_void(),
                            backdrop=shell.backdrop())
            win.swap()
    finally:
        shell.close()
        if controller:
            controller.close()
        if remote:
            remote.close()
        tracker.close()
        win.close()
        if mode == "glasses" and disp is not None:
            display_mod.restore(disp)
    return 0


def cmd_watch(args) -> int:
    """Launch the shell when glasses are plugged in; stop it when unplugged."""
    import subprocess
    child = {"proc": None}

    def start(glasses):
        if child["proc"] is None or child["proc"].poll() is not None:
            print(f"[watch] {glasses.profile.name} connected -> starting shell")
            child["proc"] = subprocess.Popen(
                [sys.executable, "-m", "zoetrope", "run",
                 "--mode", "glasses", "--media", args.media, "--tracker", args.tracker]
                + (["--library", args.library] if args.library else []))

    def stop(_):
        if child["proc"] is not None and child["proc"].poll() is None:
            print("[watch] glasses removed -> stopping shell")
            child["proc"].terminate()
            child["proc"] = None

    print("[watch] waiting for XREAL glasses (VID 0x3318)...")
    detect.monitor(start, stop)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="zoetrope", description=__doc__)
    sub = p.add_subparsers(dest="cmd")
    default_media = os.environ.get("ZOETROPE_MEDIA",
                                   os.path.join(os.path.dirname(os.path.dirname(__file__)), "media"))

    r = sub.add_parser("run", help="run the shell")
    r.add_argument("--mode", choices=["auto", "preview", "glasses"], default="auto")
    r.add_argument("--stereo", choices=["auto", "sbs", "mono"], default="auto",
                   help="auto: SBS only if the glasses expose the 3840x1080 3D mode")
    r.add_argument("--tracker", choices=["auto", "xrdriver", "hidraw", "stub"], default="auto")
    r.add_argument("--controller", choices=["auto", "daydream", "none"], default="auto",
                   help="Daydream BLE pointer (auto: use it if bleak is installed)")
    r.add_argument("--remote", type=int, nargs="?", const=8577, default=None,
                   metavar="PORT",
                   help="serve the phone web-touchpad on PORT (default 8577); "
                        "LAN-open and unauthenticated — opt-in")
    r.add_argument("--media", default=default_media)
    r.add_argument("--library", default=None,
                   help="movie library root (default: Ripsaw's library_root)")
    r.add_argument("--monitor", default=None, help="glasses monitor name (glasses mode)")
    r.add_argument("--sway", action="store_true", help="stub tracker head-sway (preview)")
    r.set_defaults(func=cmd_run)

    w = sub.add_parser("watch", help="auto-launch on plug (daemon)")
    w.add_argument("--media", default=default_media)
    w.add_argument("--library", default=None,
                   help="movie library root (default: Ripsaw's library_root)")
    w.add_argument("--tracker", choices=["auto", "xrdriver", "hidraw", "stub"], default="auto")
    w.set_defaults(func=cmd_watch)

    i = sub.add_parser("info", help="print detected glasses/display and exit")
    i.set_defaults(func=cmd_info)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if not getattr(args, "func", None):
        build_parser().print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
