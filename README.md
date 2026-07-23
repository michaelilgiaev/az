# Az'arch

<table width="100%">
<thead>
<tr><th align="left">🚧 UNDER CONSTRUCTION</th></tr>
</thead>
<tbody>
<tr><td>

This is a year-old, neglected, poorly put-together project that is undergoing a massive overhaul. Nothing works correctly yet, so please come back later.

</td></tr>
</tbody>
</table>

## Documentation

General specifications of the distribution.
- [documentation/SPECIFICATIONS_GENERAL.md](documentation/SPECIFICATIONS_GENERAL.md)

Brief overview of the components (render is hosted by GitHub Pages).
- [https://michaelilgiaev.github.io/azarch/documentation/SPECIFICATIONS_COMPONENTS_OVERVIEW.svg](https://michaelilgiaev.github.io/azarch/documentation/SPECIFICATIONS_COMPONENTS_OVERVIEW.svg)  
  (documentation/SPECIFICATIONS_COMPONENTS_OVERVIEW.svg)

Easy-to-use interactive graph of every component (render is hosted by GitHub Pages).
- [https://michaelilgiaev.github.io/azarch/documentation/SPECIFICATIONS_COMPONENTS_NAVIGATE_FULL.html](https://michaelilgiaev.github.io/azarch/documentation/SPECIFICATIONS_COMPONENTS_NAVIGATE_FULL.html)  
  (documentation/SPECIFICATIONS_COMPONENTS_NAVIGATE_FULL.html)

Plain-text raw dump of every component.
- [documentation/SPECIFICATIONS_COMPONENTS_FULL.txt](documentation/SPECIFICATIONS_COMPONENTS_FULL.txt)


## Install

1. **Download the ISO (or [compile the ISO yourself](#compile))**  
   The ISO is hosted on Google Drive (GitHub does not allow files larger than 2 GB).
   
   **Link: [https://drive.google.com/file/d/18nclTLo05_KU7uOfYd_WTnI0LK--mGE6/view?usp=sharing](https://drive.google.com/file/d/18nclTLo05_KU7uOfYd_WTnI0LK--mGE6/view?usp=sharing)**

2. **Create a Bootable USB**  

     <table width="100%">
     <thead>
     <tr><th align="left">📢❗🚨 PLEASE BE CAREFUL</th></tr>
     </thead>
     <tbody>
     <tr><td>

     This will erase everything on the USB!

     </td></tr>
     </tbody>
     </table>

   Use one of the following tools to write the ISO to a USB drive:
   - **[balenaEtcher](https://etcher.balena.io/)** (Windows/macOS/Linux)
   - **[Rufus](https://rufus.ie/en/)** (Windows only)
   - `dd` command (Linux/macOS):

     <table width="100%">
     <thead>
     <tr><th align="left">ℹ️ NOTE</th></tr>
     </thead>
     <tbody>
     <tr><td>

     - Replace `<DEVICE>` with your USB device. 
     - Replace `<DATE>` with the date on your downloaded ISO.

     </td></tr>
     </tbody>
     </table>

     ```bash
     sudo dd if=azarch-<DATE>-x86_64.iso of=/dev/<DEVICE> bs=4M status=progress && sync
     ```

3. **Boot from USB**  
   Reboot your machine and use your BIOS/UEFI boot menu to boot from the USB drive.

4. **Live Session and Installation**  
   <table width="100%">
   <thead>
   <tr><th align="left">ℹ️ NOTE</th></tr>
   </thead>
   <tbody>
   <tr><td>

   Some considerations when using the live session:
   - Reserves 4 GB of RAM.
   - Runs entirely from RAM, nothing gets saved after reboot.
   - Uses a generic open-source graphics driver.

   </td></tr>
   </tbody>
   </table>

   The ISO boots into a live session and automatically launches the Az'arch
   installer, which is powered by Calamares.

   From the live session you can:
   - Install Az'arch.
   - Perform machine rescue tasks.
   - Do general work.

## Compile

You can clone this repository and compile the ISO yourself. The first build needs an internet connection to download every component that goes into the ISO, after that everything is cached and rebuilds run fully offline. Build with Docker. The ISO is assembled with `mkarchiso`, which resolves the ISO's package list against the build host's Arch Linux repositories. That means the build only works on a genuine Arch userland with the real Arch `core`, `extra`, and `multilib` repositories. On anything else those repositories are wrong or missing and the build fails with errors like `target not found: archinstall` or endless kernel-provider prompts. Docker sidesteps all of that, the image is `archlinux:latest`, so the build runs inside real Arch no matter what machine you are on.

1. **Install Docker and Git.**

   <b>Linux</b>

   - Install both with your package manager:
     - Arch-based: `sudo pacman -S --needed docker git`
     - Debian/Ubuntu: `sudo apt update && sudo apt install docker.io git`
     - Fedora: `sudo dnf install docker git`
   - Start Docker: `sudo systemctl enable --now docker`

   <b>macOS</b>

   - Install [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/) and launch it (wait until the whale icon says Docker is running).
   - Git ships with the Xcode command line tools: `xcode-select --install`

   <b>Windows</b>

   - In an Administrator PowerShell, install WSL2: `wsl --install` (you may be prompted to reboot).
   - Install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/) and enable **"Use the WSL 2 based engine"** in its settings.
   - Open your WSL distro (e.g. Ubuntu) and install Git: `sudo apt update && sudo apt install git`

2. **Clone the repository and enter it**
   ```
   git clone https://github.com/michaelilgiaev/azarch.git && cd azarch
   ```

3. **Build the Docker image** (creates the Arch build environment)
   ```
   sudo docker build -t azarch .
   ```

4. **Compile the ISO.** The finished ISO goes to `output/`, downloaded packages
   are cached in `cache/`, and build logs go to `logs/`.

   <table width="100%">
   <thead>
   <tr><th align="left">ℹ️ NOTE</th></tr>
   </thead>
   <tbody>
   <tr><td>

   **Estimate a build before you run it.** These flags don't build or download
   anything, they just measure your machine and connection and print how long a
   build would take, then exit (no `sudo`, no privileged mounts needed). There are
   six, picking the build tier (default vs `--full-compile`) and what to estimate:

   | Flag | Tier | Estimates |
   | --- | --- | --- |
   | `--estimate` | default | compile time **and** download time |
   | `--estimate-only-compute` | default | compile time only |
   | `--estimate-only-network` | default | download time only |
   | `--estimate-full-compile` | full | compile time **and** download time |
   | `--estimate-full-compile-only-compute` | full | compile time only |
   | `--estimate-full-compile-only-network` | full | download time only |

   The compile estimate reads your CPU cores and RAM; the network estimate runs a
   short bandwidth test against an Arch mirror and divides the tier's download size
   by your measured speed. Example (estimate a full build, compute + network):

   ```
   sudo docker run --rm -it azarch --estimate
   ```

   </td></tr>
   </tbody>
   </table>

   **Default build** (recommended). Compiles only what's necessary. Everything else is downloaded as trusted, verified binaries.
   ```
   sudo docker run --rm -it --init --privileged \
     -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
     -v "$PWD/cache:/build/cache" \
     -v "$PWD/output:/build/output" \
     -v "$PWD/logs:/build/logs" \
     azarch
   ```

   **Full build.** Compiles everything from source, which takes hours.

   ```
   sudo docker run --rm -it --init --privileged \
     -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
     -v "$PWD/cache:/build/cache" \
     -v "$PWD/output:/build/output" \
     -v "$PWD/logs:/build/logs" \
     azarch --full-compile
   ```

5. **Get the ISO.** It's in the `output/` folder. On **Windows (WSL)** that folder
   opens in File Explorer at `\\wsl$\<distro>\home\<your-username>\azarch\output`.

- **Wipe the cache** to force a fresh, fully-online rebuild. Run `clear.sh`,
  which deletes the `cache/`, `output/`, and `logs/` directories:

  <table width="100%">
  <thead>
  <tr><th align="left">ℹ️ NOTE</th></tr>
  </thead>
  <tbody>
  <tr><td>

  If the compile was stopped mid-process, the ownership handback may not have run,
  so some files in `cache/` can be left root-owned. In that case wipe it with:

  ```
  sudo bash clear.sh
  ```

  </td></tr>
  </tbody>
  </table>

  ```
  bash clear.sh
  ```
