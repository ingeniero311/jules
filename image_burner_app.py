import tkinter as tk
from tkinter import ttk
import re
import os
import shutil
import subprocess
import threading
import lzma
from tkinter import messagebox
import re # Ensure re is imported, was used in burn_image_thread_worker

try:
    import requests
except ImportError:
    requests = None

class ImageBurnerApp:
    DOWNLOAD_DIR = os.path.expanduser("~/Documents/OS")
    BASE_IMAGE_URL = "https://test.wsemacomboliranas.com/imagenes/"
    DECOMPRESSED_IMG_SUFFIX = ".img"

    def __init__(self, root):
        """
        Initializes the ImageBurnerApp GUI.
        Sets up the main window, frames, widgets, and initial states.
        """
        self.root = root
        self.root.title("Raspberry Pi Image Burner")
        self.root.geometry("800x700")

        self.downloaded_image_path = None
        self.burn_process = None
        self.cancel_requested = threading.Event()
        self.download_thread = None
        self.download_response_obj = None
        self.burn_thread = None # To hold the burn thread object

        # Initial check for download directory writability
        try:
            os.makedirs(self.DOWNLOAD_DIR, exist_ok=True)
            test_file_path = os.path.join(self.DOWNLOAD_DIR, ".permissions_test")
            with open(test_file_path, "w") as f:
                f.write("test")
            os.remove(test_file_path)
        except OSError as e:
            messagebox.showerror(
                "Startup Error",
                f"Download directory {self.DOWNLOAD_DIR} is not writable or cannot be created: {e}.\n"
                "Please check permissions. The application might not function correctly."
            )
            # Consider disabling download/burn features here if this check fails critically

        # Main frame setup
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # Image list area
        image_list_frame = ttk.LabelFrame(main_frame, text="Available Images")
        image_list_frame.grid(row=0, column=0, columnspan=3, padx=5, pady=5, sticky=(tk.W, tk.E, tk.N, tk.S))
        image_list_frame.columnconfigure(0, weight=1)
        image_list_frame.rowconfigure(0, weight=1)

        self.image_listbox = tk.Listbox(image_list_frame)
        self.image_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.image_listbox.bind('<<ListboxSelect>>', self.on_image_select)

        # Buttons for image operations
        image_button_frame = ttk.Frame(main_frame)
        image_button_frame.grid(row=1, column=0, columnspan=3, padx=5, pady=5, sticky=(tk.W, tk.E))

        self.refresh_images_button = ttk.Button(image_button_frame, text="Refresh Images", command=self.fetch_and_display_images)
        self.refresh_images_button.grid(row=0, column=0, padx=5, pady=5)

        self.download_button = ttk.Button(image_button_frame, text="Download Selected Image", command=self.download_selected_image, state=tk.DISABLED)
        self.download_button.grid(row=0, column=1, padx=5, pady=5)

        # Device Selection Area
        device_frame = ttk.LabelFrame(main_frame, text="Select Target Device")
        device_frame.grid(row=2, column=0, columnspan=3, padx=5, pady=5, sticky=(tk.W, tk.E))
        device_frame.columnconfigure(0, weight=1)

        self.device_combobox = ttk.Combobox(device_frame, state="readonly", width=40)
        self.device_combobox.grid(row=0, column=0, padx=5, pady=5, sticky=(tk.W, tk.E))
        self.device_combobox.set("Click 'Refresh Devices' to load.")
        self.device_combobox.bind('<<ComboboxSelected>>', self.on_device_select)

        self.refresh_devices_button = ttk.Button(device_frame, text="Refresh Devices", command=self.refresh_devices)
        self.refresh_devices_button.grid(row=0, column=1, padx=5, pady=5)

        # Burn and Cancel Buttons now below device selection
        burn_cancel_frame = ttk.Frame(main_frame)
        burn_cancel_frame.grid(row=3, column=0, columnspan=3, padx=5, pady=5, sticky=(tk.W, tk.E))

        self.burn_button = ttk.Button(burn_cancel_frame, text="Burn Image to SD Card", command=self.start_burn_process, state=tk.DISABLED)
        self.burn_button.grid(row=0, column=0, padx=5, pady=5)

        self.cancel_button = ttk.Button(burn_cancel_frame, text="Cancel Operation", command=self.request_cancel_current_operation, state=tk.DISABLED) # Renamed command
        self.cancel_button.grid(row=0, column=1, padx=5, pady=5)

        # Status and Progress area
        status_frame = ttk.LabelFrame(main_frame, text="Status and Progress")
        status_frame.grid(row=4, column=0, columnspan=3, padx=5, pady=5, sticky=(tk.W, tk.E)) # Adjusted row
        status_frame.columnconfigure(0, weight=1)

        self.status_label = ttk.Label(status_frame, text="Status: Idle")
        self.status_label.grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)

        self.progress_bar = ttk.Progressbar(status_frame, orient=tk.HORIZONTAL, mode='determinate')
        self.progress_bar.grid(row=1, column=0, padx=5, pady=5, sticky=(tk.W, tk.E))

        # Bottom buttons
        bottom_button_frame = ttk.Frame(main_frame)
        bottom_button_frame.grid(row=5, column=0, columnspan=3, sticky=(tk.E))

        self.close_button = ttk.Button(bottom_button_frame, text="Close Application", command=self.on_closing) # Command changed
        self.close_button.grid(row=0, column=0, padx=5, pady=5)

        # Configure main_frame grid weights
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(0, weight=1) # Image list frame
        # main_frame.rowconfigure(2) # device frame - default weight 0
        # main_frame.rowconfigure(4) # status frame - default weight 0

        self.refresh_devices()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        print("DEBUG: ImageBurnerApp.__init__ completed.")
        print(f"DEBUG: 'on_closing' method available in self: {hasattr(self, 'on_closing')}")

    def update_gui_status(self, status_text=None, progress_value=None, operation_active=None):
        """
        Updates GUI elements like status label, progress bar, and button states.
        This method is designed to be called safely from the main thread or scheduled via root.after_idle.

        Args:
            status_text (str, optional): Text to set for the status label.
            progress_value (int, optional): Value to set for the progress bar.
            operation_active (bool, optional): Explicitly sets if an operation is active.
                                            If None, it's inferred from download/burn thread states.
        """
        if status_text is not None:
            self.status_label.config(text=f"Status: {status_text}")
        if progress_value is not None:
            self.progress_bar['value'] = progress_value

        is_download_active = bool(self.download_thread and self.download_thread.is_alive())
        is_burn_active = bool(self.burn_process and self.burn_process.poll() is None)

        # If operation_active is explicitly passed, use it. Otherwise, infer from thread/process state.
        # This helps manage UI state immediately when an operation starts, before thread/process objects are fully populated.
        currently_active = operation_active if operation_active is not None else (is_download_active or is_burn_active)

        if currently_active:
            self.download_button.config(state=tk.DISABLED)
            self.burn_button.config(state=tk.DISABLED)
            self.refresh_images_button.config(state=tk.DISABLED)
            self.refresh_devices_button.config(state=tk.DISABLED)
            self.device_combobox.config(state=tk.DISABLED)
            self.image_listbox.config(state=tk.DISABLED)
            self.cancel_button.config(state=tk.NORMAL)
        else: # No operation active
            self.cancel_button.config(state=tk.DISABLED)
            self.refresh_images_button.config(state=tk.NORMAL)
            self.refresh_devices_button.config(state=tk.NORMAL)
            try:
                self.device_combobox.config(state='readonly')
            except tk.TclError:
                 self.device_combobox.config(state=tk.DISABLED)
            self.image_listbox.config(state=tk.NORMAL)
            self.on_image_select() # Re-evaluates download button state
            self.update_burn_button_state()

    def update_burn_button_state(self):
        """
        Updates the state of the 'Burn Image' button based on whether an image is downloaded
        and a target device is selected, and no other operation is currently active.
        """
        is_download_active = bool(self.download_thread and self.download_thread.is_alive())
        is_burn_active = bool(self.burn_process and self.burn_process.poll() is None)

        if is_download_active or is_burn_active: # If any operation is active, burn button is disabled
            self.burn_button.config(state=tk.DISABLED)
            return

        has_image = bool(self.downloaded_image_path)
        selected_device_value = self.device_combobox.get()
        has_device = bool(selected_device_value and \
                          selected_device_value != "Click 'Refresh Devices' to load." and \
                          selected_device_value != "No suitable devices found." and \
                          selected_device_value != "Scanning..." and \
                          selected_device_value != "Error: lsblk not found." and \
                          selected_device_value != "Error listing devices." and \
                          selected_device_value != "Error processing devices.")

        if has_image and has_device:
            self.burn_button.config(state=tk.NORMAL)
        else:
            self.burn_button.config(state=tk.DISABLED)

    def on_image_select(self, event=None):
        """
        Handles the event when an image is selected in the listbox.
        Updates download button state and status message based on whether the selected
        image (or any other image) already exists locally.
        """
        if self.image_listbox.curselection():
            selected_img_name = self.image_listbox.get(self.image_listbox.curselection()[0])
            existing_img_path = self.check_existing_image() # This updates self.downloaded_image_path

            if existing_img_path:
                self.download_button.config(state=tk.DISABLED)
                if os.path.basename(existing_img_path) == selected_img_name:
                    self.root.after_idle(self.update_gui_status, status_text=f"Selected image {selected_img_name} already exists locally.")
                else:
                    self.root.after_idle(self.update_gui_status, status_text=f"Another image ({os.path.basename(existing_img_path)}) exists. Remove it to download a new one.")
            else:
                self.download_button.config(state=tk.NORMAL)
                self.root.after_idle(self.update_gui_status, status_text="Image selected. Ready to download.")
        else:
            self.download_button.config(state=tk.DISABLED)
        self.update_burn_button_state()

    def on_device_select(self, event=None):
        """Handles the event when a device is selected from the combobox."""
        self.update_burn_button_state()

    def check_existing_image(self):
        """
        Checks if an .img.xz file exists in the download directory.
        Sets self.downloaded_image_path to the found image path, otherwise sets it to None.
        Returns:
            str: Path to the existing image if found, else None.
        """
        os.makedirs(self.DOWNLOAD_DIR, exist_ok=True)
        for item in os.listdir(self.DOWNLOAD_DIR):
            if item.endswith(".img.xz"):
                self.downloaded_image_path = os.path.join(self.DOWNLOAD_DIR, item)
                return self.downloaded_image_path
        self.downloaded_image_path = None # Ensure it's None if no image is found
        return None

    def fetch_and_display_images(self):
        """
        Fetches the list of image filenames from the BASE_IMAGE_URL,
        updates the image listbox, and manages related UI states.
        """
        print("DEBUG: fetch_and_display_images() method called.")
        if (self.download_thread and self.download_thread.is_alive()) or \
           (self.burn_process and self.burn_process.poll() is None): # Check if any operation is active
            self.root.after_idle(self.update_gui_status, status_text="Operation in progress. Cannot refresh images now.")
            return
        if not requests:
            self.root.after_idle(self.update_gui_status, status_text="Error - 'requests' library not installed.")
            print("Error: 'requests' library is not available. Please install it using 'pip install requests'")
            return

        self.status_label.config(text="Status: Fetching images...")
        self.image_listbox.delete(0, tk.END) # Clear listbox first

        # This call updates self.downloaded_image_path if an image exists
        existing_image_path = self.check_existing_image()

        if existing_image_path:
            self.status_label.config(text=f"Status: Existing image: {os.path.basename(existing_image_path)}. Select it or remove to download new.")
            self.download_button.config(state=tk.DISABLED)
            print(f"Existing image found: {existing_image_path}. Download button disabled.")
        else:
            self.download_button.config(state=tk.DISABLED)
            self.root.after_idle(self.update_gui_status, status_text="Fetching image list...")

        try:
            response = requests.get(self.BASE_IMAGE_URL, timeout=10)
            response.raise_for_status()

            image_pattern = re.compile(r"[A-Za-z0-9_]+_CM4_[A-Za-z0-9.]+\.img\.xz")
            filenames = image_pattern.findall(response.text)

            if filenames:
                unique_filenames = sorted(list(set(filenames)))
                selected_idx_to_restore = -1

                for i, name in enumerate(unique_filenames):
                    self.image_listbox.insert(tk.END, name)
                    if existing_image_path and os.path.basename(existing_image_path) == name:
                        selected_idx_to_restore = i

                if selected_idx_to_restore != -1:
                    self.image_listbox.selection_set(selected_idx_to_restore)
                    self.image_listbox.see(selected_idx_to_restore)
                    self.root.after_idle(self.update_gui_status, status_text=f"Existing image {os.path.basename(existing_image_path)} found and selected.")
                elif not existing_image_path :
                    self.root.after_idle(self.update_gui_status, status_text=f"{len(unique_filenames)} images loaded. Select an image.")

                print(f"Successfully fetched {len(unique_filenames)} image filenames.")
            else:
                if not existing_image_path:
                    self.root.after_idle(self.update_gui_status, status_text="No matching image files found on the server.")
                print("No matching image files found on the server.")

        except requests.exceptions.RequestException as e:
            self.root.after_idle(self.update_gui_status, status_text=f"Error fetching images: {e}")
            print(f"Error fetching images: {e}")
        except Exception as e:
            print(f"DEBUG: fetch_and_display_images caught generic exception: {type(e).__name__} - {e}")
            err_msg = f"Unexpected error during refresh: {type(e).__name__} - {e}"
            self.root.after_idle(self.update_gui_status, status_text=err_msg)
            print(err_msg)

        self.on_image_select()
        self.update_burn_button_state()

    def download_selected_image(self):
        if (self.download_thread and self.download_thread.is_alive()) or \
           (self.burn_process and self.burn_process.poll() is None):
            self.root.after_idle(self.update_gui_status, status_text="Operation in progress. Cannot download now.")
            return
        if not self.image_listbox.curselection():
            self.root.after_idle(self.update_gui_status, status_text="No image selected for download.")
            return

        selected_index = self.image_listbox.curselection()[0]
        image_filename = self.image_listbox.get(selected_index)

        # Re-check before download, this is crucial.
        # This call to check_existing_image also updates self.downloaded_image_path
        if self.check_existing_image():
            self.status_label.config(text=f"Status: Image {os.path.basename(self.downloaded_image_path)} already exists. Remove it first.")
            self.download_button.config(state=tk.DISABLED)
            return

        # Explicitly clear before starting download, as check_existing_image might have set it if user clicked around
        self.downloaded_image_path = None
        os.makedirs(self.DOWNLOAD_DIR, exist_ok=True)
        current_download_path = os.path.join(self.DOWNLOAD_DIR, image_filename)
        image_url = self.BASE_IMAGE_URL + image_filename # Define image_url here

        self.cancel_requested.clear()
        self.root.after_idle(self.update_gui_status, operation_active=True, status_text=f"Preparing to download {image_filename}...")

        self.download_thread = threading.Thread(
            target=self._download_thread_worker,
            args=(image_filename, current_download_path, image_url) # Pass image_url
        )
        self.download_thread.daemon = True
        self.download_thread.start()

    def _download_thread_worker(self, image_filename, download_path, image_url):
        try:
            self.root.after_idle(self.update_gui_status, status_text=f"Downloading {image_filename}...", progress_value=0)

            self.download_response_obj = requests.get(image_url, stream=True, timeout=30)
            self.download_response_obj.raise_for_status()

            total_size = int(self.download_response_obj.headers.get('content-length', 0))
            bytes_downloaded = 0

            with open(download_path, 'wb') as f:
                for chunk in self.download_response_obj.iter_content(chunk_size=8192):
                    if self.cancel_requested.is_set():
                        raise OperationCancelledError("Download cancelled by user.")
                    if chunk:
                        f.write(chunk)
                        bytes_downloaded += len(chunk)
                        if total_size > 0:
                            progress = (bytes_downloaded / total_size) * 100
                            self.root.after_idle(self.update_gui_status, status_text=f"Downloading {image_filename}... {int(progress)}%", progress_value=progress)
                        else:
                            self.root.after_idle(self.update_gui_status, status_text=f"Downloading {image_filename}... (size unknown)")

            if self.cancel_requested.is_set(): # Check again after loop
                raise OperationCancelledError("Download cancelled by user.")

            self.root.after_idle(self.update_gui_status, status_text=f"{image_filename} downloaded successfully.", progress_value=100)
            self.downloaded_image_path = download_path
            # UI update for button state will be handled by update_gui_status(operation_active=False) in finally

        except OperationCancelledError as oce:
            self.root.after_idle(self.update_gui_status, status_text=str(oce), progress_value=0)
            if os.path.exists(download_path): os.remove(download_path)
            self.downloaded_image_path = None
            print(str(oce))
        except requests.exceptions.RequestException as e:
            self.root.after_idle(self.update_gui_status, status_text=f"Download error: {e}", progress_value=0)
            if os.path.exists(download_path): os.remove(download_path)
            self.downloaded_image_path = None
            print(f"Download error for {image_filename}: {e}")
        except (IOError, PermissionError) as e:
            error_msg = f"File system error (check permissions for {self.DOWNLOAD_DIR}): {e}"
            self.root.after_idle(self.update_gui_status, status_text=error_msg, progress_value=0)
            if os.path.exists(download_path): os.remove(download_path)
            self.downloaded_image_path = None
            print(f"File error for {image_filename}: {e}")
        except Exception as e:
            self.root.after_idle(self.update_gui_status, status_text=f"An unexpected download error: {e}", progress_value=0)
            if os.path.exists(download_path): os.remove(download_path) # Cleanup partial file
            self.downloaded_image_path = None
            # print(f"An unexpected error during download of {image_filename}: {e}") # Keep for important debugging
        finally:
            if self.download_response_obj and hasattr(self.download_response_obj, 'raw') and \
               self.download_response_obj.raw and not self.download_response_obj.raw.closed:
                self.download_response_obj.raw.close()
            self.download_response_obj = None
            self.download_thread = None
            if not self.cancel_requested.is_set(): # Only clear if not cancelled, as on_closing might need it
                self.cancel_requested.clear()
            self.root.after_idle(self.update_gui_status, operation_active=False)


    def refresh_devices(self):
        """
        Refreshes the list of storage devices using 'lsblk'.
        Filters devices and populates the device selection combobox.
        """
        if (self.download_thread and self.download_thread.is_alive()) or \
           (self.burn_process and self.burn_process.poll() is None): # Check if any operation is active
            self.root.after_idle(self.update_gui_status, status_text="Operation in progress. Cannot refresh devices now.")
            return

        self.root.after_idle(self.update_gui_status, status_text="Refreshing device list...")
        self.device_combobox.set("Scanning...")
        self.device_combobox['values'] = []

        try:
            result = subprocess.run(
                ['lsblk', '-ndo', 'NAME,SIZE,TYPE,MOUNTPOINT'],
                capture_output=True, text=True, check=True, timeout=5
            )
            devices = []
            output_lines = result.stdout.strip().split('\n')

            # print("lsblk raw output:\n", result.stdout) # Keep commented for normal use

            for line in output_lines:
                parts = line.strip().split() # Simple split, assumes no spaces in NAME, SIZE, TYPE
                if not parts: continue

                name = parts[0]
                size = parts[1] if len(parts) > 1 else "N/A"
                dev_type = parts[2] if len(parts) > 2 else "N/A"
                mountpoint = parts[3] if len(parts) > 3 else ""

                # More robust parsing for mountpoint if it contains spaces (though lsblk -n should avoid this unless it's the last field)
                # For -ndo NAME,SIZE,TYPE,MOUNTPOINT, mountpoint is everything after type if type exists.
                if dev_type != "N/A" and len(parts) > 3 :
                    mountpoint = line.strip().split(dev_type, 1)[1].strip().split(maxsplit=1)[1] if len(line.strip().split(dev_type, 1)[1].strip().split(maxsplit=1)) > 1 else ""


                device_path = f"/dev/{name}"
                # Filter logic:
                # 1. Must be of type 'disk'.
                # 2. Not mmcblk0 (common RPi main card).
                # 3. Not mounted on critical paths.
                # 4. Name should suggest a removable drive (sdX, nvmeXnY).
                critical_mounts = ['/', '/boot', '[SWAP]'] # Add /usr, /var if needed
                is_critical_mount = False
                if mountpoint:
                    for crit_mp in critical_mounts:
                        if mountpoint == crit_mp or mountpoint.startswith(crit_mp + '/'):
                            is_critical_mount = True
                            break

                is_potential_target = dev_type == 'disk' and \
                                     not name.startswith('mmcblk0') and \
                                     not name.startswith('loop') and \
                                     not name.startswith('zram') and \
                                     not is_critical_mount #and \
                                     # (name.startswith('sd') or name.startswith('nvme')) # This might be too restrictive

                if is_potential_target:
                    devices.append(f"{device_path} - {size}")

            if devices:
                self.device_combobox['values'] = devices
                self.device_combobox.set(devices[0])
                self.root.after_idle(self.update_gui_status, status_text=f"{len(devices)} potential devices found. Verify selection.")
            else:
                self.device_combobox.set("No suitable devices found.")
                self.root.after_idle(self.update_gui_status, status_text="No suitable target devices found. Check connections/permissions.")
            # print(f"Filtered devices for combobox: {devices}") # Keep commented for normal use

        except FileNotFoundError:
            self.root.after_idle(self.update_gui_status, status_text="Error: 'lsblk' command not found. Ensure it's installed and in PATH.")
            self.device_combobox.set("Error: lsblk not found.")
            print("Error: 'lsblk' command not found.")
        except subprocess.TimeoutExpired:
            self.root.after_idle(self.update_gui_status, status_text="Error - 'lsblk' command timed out.")
            self.device_combobox.set("Error: lsblk timeout.")
            print("Error: 'lsblk' command timed out.")
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else e.stdout
            self.root.after_idle(self.update_gui_status, status_text=f"Error running lsblk: {error_msg[:100]}") # Show first 100 chars
            self.device_combobox.set("Error listing devices.")
            print(f"Error running lsblk: {error_msg}") # Log the full error
        except Exception as e:
            self.root.after_idle(self.update_gui_status, status_text=f"Error processing device list: {str(e)[:100]}") # Show truncated error
            self.device_combobox.set("Error processing devices.")
            # print(f"Error processing device list: {e}") # Keep for important debugging
        finally:
            self.update_burn_button_state()

    def start_burn_process(self):
        """
        Initiates the image burning process.
        Performs pre-checks, shows a confirmation dialog, and starts the burn worker thread.
        """
        if not self.downloaded_image_path:
            messagebox.showerror("Error", "No image file has been downloaded or identified for burning.")
            return

        selected_device_str = self.device_combobox.get()
        if not selected_device_str or not selected_device_str.startswith("/dev/"):
            messagebox.showerror("Error", "No valid target device selected.")
            return

        target_device = selected_device_str.split(" - ")[0]

        confirmation = messagebox.askyesno(
            "Confirm Overwrite",
            f"WARNING: This will overwrite all data on {target_device} with the image {os.path.basename(self.downloaded_image_path)}.\n\n"
            "This operation is IRREVERSIBLE.\n\n"
            "Are you absolutely sure you want to proceed?",
            icon='warning'
        )

        if not confirmation:
            self.root.after_idle(self.update_gui_status, status_text="Burn operation cancelled by user.", operation_active=False)
            return

        self.cancel_requested.clear()
        # Pass operation_active=True to immediately disable UI components
        self.root.after_idle(self.update_gui_status, status_text="Starting burn process...", operation_active=True, progress_value=0)

        if self.burn_process and self.burn_process.poll() is None: # Should not happen due to UI disable
             self.root.after_idle(self.update_gui_status, status_text="Another burn process is already active.", operation_active=False)
             return

        # Assign to self.burn_thread, not a local var
        self.burn_thread = threading.Thread(
            target=self.burn_image_thread_worker,
            args=(target_device, self.downloaded_image_path)
        )
        self.burn_thread.daemon = True
        self.burn_thread.start()

    def request_cancel_current_operation(self): # Renamed from cancel_burn_operation
        self.root.after_idle(self.update_gui_status, status_text="Cancellation requested...")
        self.cancel_requested.set() # Signal all worker threads

        # Specific cancellation for ongoing download (gentle first)
        if self.download_thread and self.download_thread.is_alive() and self.download_response_obj:
            try:
                print("Attempting to close download stream...")
                self.download_response_obj.raw.close()
            except Exception as e:
                print(f"Error closing download stream: {e}")

        # Specific cancellation for ongoing burn (dd process)
        if self.burn_process and self.burn_process.poll() is None:
            try:
                print(f"Attempting to terminate dd process PID {self.burn_process.pid}...")
                kill_command = ['sudo', 'kill', '-SIGTERM', str(self.burn_process.pid)]
                term_proc = subprocess.run(kill_command, timeout=2, check=False, capture_output=True, text=True)
                if term_proc.returncode != 0 :
                    print(f"SIGTERM failed for PID {self.burn_process.pid} (exit code {term_proc.returncode}). Stderr: {term_proc.stderr}. Trying SIGKILL.")
                    kill_command = ['sudo', 'kill', '-SIGKILL', str(self.burn_process.pid)]
                    subprocess.run(kill_command, timeout=1, check=False, capture_output=True, text=True)
                print(f"Sent SIGTERM/SIGKILL to dd process PID {self.burn_process.pid}")
            except FileNotFoundError: # sudo or kill command not found
                err_msg = "Error cancelling: 'sudo' or 'kill' command not found."
                print(err_msg)
                self.root.after_idle(self.update_gui_status, status_text=err_msg)
            except subprocess.TimeoutExpired:
                 print(f"Timeout trying to kill dd process PID {self.burn_process.pid}")
                 self.root.after_idle(self.update_gui_status, status_text="Timeout trying to cancel dd.")
            except Exception as e:
                err_msg = f"Error cancelling dd: {str(e)[:100]}"
                print(f"Error trying to terminate/kill dd process {self.burn_process.pid}: {e}")
                self.root.after_idle(self.update_gui_status, status_text=err_msg)
        # Worker threads handle their own cleanup. update_gui_status(operation_active=False) called by worker's finally.

    def on_closing(self):
        """Handles the application close request (e.g., from window manager or close button)."""
        print("DEBUG: on_closing() method called.")
        is_download_active = bool(self.download_thread and self.download_thread.is_alive())
        is_burn_active = bool(self.burn_thread and self.burn_thread.is_alive()) # Check thread
        # Also check burn_process directly in case thread ended but process termination is pending
        if not is_burn_active and self.burn_process:
            is_burn_active = self.burn_process.poll() is None

        if is_download_active or is_burn_active:
            if messagebox.askyesno("Confirm Exit",
                                   "An operation is currently in progress. Exiting now will cancel it.\n"
                                   "Are you sure you want to exit?"):
                self.root.after_idle(self.update_gui_status, status_text="Exit requested. Cancelling operations...")
                self.cancel_requested.set() # Signal threads first
                self.request_cancel_current_operation() # Attempt to actively stop ongoing I/O or processes

                if self.download_thread and self.download_thread.is_alive():
                    print("Waiting for download thread to join...")
                    self.download_thread.join(timeout=0.5)
                if self.burn_thread and self.burn_thread.is_alive():
                    print("Waiting for burn thread to join...")
                    self.burn_thread.join(timeout=1.0) # Burn might need a bit longer for dd/sudo kill

                self.root.destroy()
            else:
                return # Do not close, user cancelled exit
        else:
            self.root.destroy() # No operations active, close directly

    def _decompress_image_worker(self, image_path_xz, decompressed_image_path):
        """Worker part for decompressing the image. Runs in burn_image_thread_worker."""
        self.root.after_idle(self.update_gui_status, status_text=f"Decompressing {os.path.basename(image_path_xz)}...", progress_value=0)
        with lzma.open(image_path_xz, 'rb') as f_in, open(decompressed_image_path, 'wb') as f_out:
            chunk_size = 4 * 1024 * 1024 # 4MB
            # For actual progress, we'd need uncompressed size if available, or estimate
            # For now, just indicate activity.
            idx = 0
            while True:
                if self.cancel_requested.is_set():
                    raise OperationCancelledError("Decompression cancelled.")
                chunk = f_in.read(chunk_size)
                if not chunk:
                    break
                f_out.write(chunk)
                idx +=1
                # Simple visual feedback of ongoing decompression
                self.root.after_idle(self.update_gui_status, progress_value=(idx*5 % 20)) # 0,5,10,15 then repeat
        if self.cancel_requested.is_set(): raise OperationCancelledError("Decompression cancelled.")
        self.root.after_idle(self.update_gui_status, status_text="Decompression complete.", progress_value=25)


    def _burn_dd_worker(self, target_device, decompressed_image_path):
        """Worker part for burning the image with dd. Runs in burn_image_thread_worker."""
        dd_command = ['sudo', 'dd', f'if={decompressed_image_path}', f'of={target_device}', 'bs=4M', 'status=progress', 'conv=fsync']
        self.root.after_idle(self.update_gui_status, status_text=f"Burning image to {target_device} using dd...")

        process = subprocess.Popen(dd_command, stderr=subprocess.PIPE, text=True, bufsize=1, universal_newlines=True)
        self.burn_process = process

        dd_progress_regex = re.compile(r'(\d+)\s*bytes')
        while True:
            if self.cancel_requested.is_set():
                if process.poll() is None:
                    subprocess.run(['sudo', 'kill', '-SIGTERM', str(process.pid)], timeout=2, check=False)
                    if process.poll() is None: subprocess.run(['sudo', 'kill', '-SIGKILL', str(process.pid)], timeout=1, check=False)
                    process.wait()
                raise OperationCancelledError("Burn cancelled during dd.")

            line = process.stderr.readline()
            if not line and process.poll() is not None: break
            if line:
                # print(f"dd stderr: {line.strip()}") # Keep commented for normal use
                match = dd_progress_regex.search(line)
                if match:
                    bytes_copied_str = match.group(1)
                    try:
                        # This is a rough estimate as total size isn't readily available from xz without full decompress
                        progress_val = 25 + (int(bytes_copied_str) % 500000000 // 7000000) # Heuristic: 25-95%
                        self.root.after_idle(self.update_gui_status, progress_value=min(progress_val, 95), status_text=f"Burning... {line.strip()[:50]}")
                    except ValueError:
                         self.root.after_idle(self.update_gui_status, status_text=f"dd: {line.strip()[:70]}")

        return_code = process.wait()
        self.burn_process = None
        if self.cancel_requested.is_set(): raise OperationCancelledError("Burn cancelled after dd completion.")
        return return_code


    def burn_image_thread_worker(self, target_device, image_path_xz):
        """
        Handles the image burning process in a separate thread.
        This includes decompressing the image and writing it with 'dd'.
        """
        decompressed_image_path = os.path.join(self.DOWNLOAD_DIR, os.path.basename(image_path_xz).replace(".img.xz", self.DECOMPRESSED_IMG_SUFFIX))

        try:
            self._decompress_image_worker(image_path_xz, decompressed_image_path)

            # If cancel was requested during decompression, error would have been raised.
            # Now proceed to burning.
            return_code = self._burn_dd_worker(target_device, decompressed_image_path)

            if return_code == 0:
                self.root.after_idle(self.update_gui_status, status_text=f"Image burned successfully to {target_device}.", progress_value=100)
            else:
                error_output = process.stderr.read() if hasattr(process.stderr, 'read') else ""
                final_error_msg = f"Error burning image (dd exit code {return_code})."
                if "Permission denied" in error_output or "Operation not permitted" in error_output:
                    final_error_msg += " Try running the application with sudo."
                elif error_output:
                    final_error_msg += f" Details: {error_output.strip()[:100]}"
                self.root.after_idle(self.update_gui_status, status_text=final_error_msg, progress_value=0)
                raise Exception(final_error_msg)

        except OperationCancelledError as oce:
            self.root.after_idle(self.update_gui_status, status_text=str(oce), progress_value=0)
            print(str(oce))
        except lzma.LZMAError as e:
            self.root.after_idle(self.update_gui_status, status_text=f"Decompression error: {e}", progress_value=0)
            print(f"Decompression error: {e}")
        except FileNotFoundError as e: # Covers dd command not found, or image file disappearing
            self.root.after_idle(self.update_gui_status, status_text=f"File operation error: {e}", progress_value=0)
            print(f"File error during burn phase: {e}")
        except (IOError, PermissionError) as e: # Covers failed write of decompressed image
            error_msg = f"File system error during decompression/burn (check permissions for {self.DOWNLOAD_DIR}): {e}"
            self.root.after_idle(self.update_gui_status, status_text=error_msg, progress_value=0)
            print(error_msg)
        except subprocess.SubprocessError as e: # Covers dd execution issues other than not found
            self.root.after_idle(self.update_gui_status, status_text=f"dd command execution error: {e}", progress_value=0)
            print(f"dd execution error: {e}")
        except Exception as e:
            self.root.after_idle(self.update_gui_status, status_text=f"An unexpected error in burn process: {str(e)[:100]}", progress_value=0)
            print(f"Unexpected burn error: {e}")
        finally:
            if os.path.exists(decompressed_image_path):
                try:
                    os.remove(decompressed_image_path)
                    print(f"Cleaned up: {decompressed_image_path}")
                except OSError as e:
                    print(f"Error cleaning up {decompressed_image_path}: {e}")

            self.burn_process = None
            # self.cancel_requested.clear() # Do not clear here, on_closing might need it
            # Let on_closing or next operation clear it.
            self.root.after_idle(self.update_gui_status, operation_active=False)

class OperationCancelledError(Exception):
    pass

if __name__ == "__main__":
    root = tk.Tk()
    app = ImageBurnerApp(root)
    # on_closing is bound in __init__
    print("Application window created. Starting main loop...")
    app.fetch_and_display_images()
    root.mainloop()
