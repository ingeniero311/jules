# Raspberry Pi Image Burner

A Python GUI application for downloading OS images and burning them to a microSD card on a Raspberry Pi (or other Linux systems).

## Features

*   Lists available OS images from a predefined URL.
*   Downloads selected OS images (`.img.xz` format).
*   Manages a local cache: only one image is stored locally (`~/Documents/OS/`); prevents re-download if an image exists.
*   Decompresses `.xz` archives before burning.
*   Lists available block devices (potential microSD cards), with basic filtering to avoid common system disks.
*   Burns the `.img` file to the selected microSD card using `dd`.
*   Displays progress for download and burning operations.
*   Allows cancellation of ongoing operations.
*   Graphical user interface built with `tkinter`.

## Prerequisites

*   **Python 3:** The script is written for Python 3.
*   **tkinter:** Usually included with standard Python installations. If not, you may need to install it (e.g., `sudo apt-get install python3-tk` on Debian/Ubuntu based systems).
*   **requests library:** For fetching images from the internet. Install it using pip:
    ```bash
    pip install requests
    ```
*   **`lsblk` command:** Used to list available block devices. Typically pre-installed on most Linux distributions.
*   **`dd` command:** Used for burning the image. A standard Linux utility.
*   **`xz` utils:** For decompressing `.xz` archives. Usually pre-installed. If not (e.g., `lzma` module error or `xz` command not found during decompression attempt by script), install with:
    ```bash
    sudo apt-get install xz-utils
    ```

## How to Run

1.  Clone this repository or download the `image_burner_app.py` script.
2.  Ensure all prerequisites are installed.
3.  Open a terminal and navigate to the directory containing the script.
4.  **Important:** The image burning operation (`dd`) requires root privileges to write to block devices. Therefore, you will likely need to run the script using `sudo`:
    ```bash
    sudo python3 image_burner_app.py
    ```
    If you run without `sudo`, the script will attempt to use `sudo dd` internally, and you will be prompted for your password by the system when the burn starts. However, running the entire script with `sudo` is often more straightforward.

## Usage

1.  **Refresh Images:** Click to fetch the latest list of available OS images.
2.  **Select Image:** Click on an image in the "Available Images" list.
3.  **Download Image:** Click to download the selected image. It will be saved to `~/Documents/OS/`. Only one image can be present here at a time.
4.  **Refresh Devices:** Click to scan for connected block devices suitable for burning (e.g., USB microSD card readers).
5.  **Select Target Device:** Carefully choose your microSD card from the dropdown list. **WARNING: CHOOSING THE WRONG DEVICE CAN RESULT IN COMPLETE DATA LOSS ON THAT DEVICE.** Double-check your selection.
6.  **Burn Image:** After confirming your selection, click to start decompressing and writing the image to the microSD card. Progress will be displayed.
7.  **Cancel Operation:** Click to attempt to stop an ongoing download or burn process.
8.  **Close Application:** Click to exit the program. You will be prompted if an operation is in progress.

## Image Storage

*   Downloaded images (`.img.xz`) are stored in `~/Documents/OS/`.
*   Decompressed images (`.img`) are temporarily stored in the same directory during the burn process and are cleaned up afterwards.

## Disclaimer

This script interacts directly with disk devices. The authors are not responsible for any data loss that may occur from misuse or errors in device selection. **Always double-check the target device before starting the burn process.**
