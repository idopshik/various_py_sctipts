import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from pathlib import Path
import os
import shutil
import sys
import codecs
import configparser
from typing import Dict, Optional, Tuple, List, Union
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import find_peaks
from scipy import interpolate
from tqdm import tqdm
import can
import cantools
import logging

# Set UTF-8 encoding for console output
sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

# Debug flag for detailed output
DEBUG = False
SAVE_MORE = False
INIFILE = ".\P-V_gui_preparer\config.ini"

PRESSURE_COLUMNS = [
    "FL_BrakePressure_a1",
    "FR_BrakePressure_a2",
    "RL_BrakePressure_a3",
    "RR_BrakePressure_a4",
    "MC2_BrakePressure_a5",
]

def setup_logger(debug: bool = False, name: Optional[str] = None) -> logging.Logger:
    """
    Configure and return a logger instance.

    Args:
        debug (bool): If True, set log level to DEBUG, else INFO.
        name (Optional[str]): Optional logger name.

    Returns:
        logging.Logger: Configured logger.
    """
    logger = logging.getLogger(name or "blf_tool")
    logger.setLevel(logging.DEBUG if debug else logging.INFO)

    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger

class BLFConfigurator:
    """GUI for configuring BLF log processing parameters."""
    def __init__(self) -> None:
        self.filename: str = ""
        self.blf_path: str = ""
        self.csv_path: str = ""
        self.dbc_path: str = ""
        self.start: Optional[float] = None
        self.stop: Optional[float] = None
        self.check_options: Dict[str, bool] = {
            "auto cut": False,
            "first msg calib": True,
            "Pressure-time graph": False,
            "All pressures graph": True,  # Enabled by default for pressure vs. travel
            "Interactive graph": False,
            "preserve paths": False
        }


        self.ini_file: str = INIFILE
        self.load_from_ini()
        self.ok_pressed: bool = False

    def load_from_ini(self) -> None:
        """Load configuration from INI file."""
        config = configparser.ConfigParser()
        if os.path.exists(self.ini_file):
            config.read(self.ini_file)
            if 'Settings' in config:
                for key in self.check_options:
                    print(f"Loaded {key}: {self.check_options[key]}")
                    if key in config['Settings']:
                        self.check_options[key] = config['Settings'].getboolean(key)
                if 'blf_path' in config['Settings']:
                    self.blf_path = config['Settings']['blf_path']
                if 'csv_path' in config['Settings']:
                    self.csv_path = config['Settings']['csv_path']
                if 'dbc_path' in config['Settings']:
                    self.dbc_path = config['Settings']['dbc_path']

    def save_to_ini(self) -> None:
        """Save configuration to INI file."""
        config = configparser.ConfigParser()
        config['Settings'] = {key: str(value) for key, value in self.check_options.items()}
        config['Settings']['dbc_path'] = self.dbc_path
        if self.check_options["preserve paths"]:
            config['Settings']['blf_path'] = self.blf_path
            config['Settings']['csv_path'] = self.csv_path
        with open(self.ini_file, 'w') as configfile:
            config.write(configfile)

    def select_blf(self) -> None:
        """Open file dialog to select BLF file."""
        file_path = filedialog.askopenfilename(filetypes=[("BLF files", "*.blf")])
        if file_path:
            self.blf_entry.delete(0, tk.END)
            self.blf_entry.insert(0, os.path.abspath(file_path))

    def select_csv(self) -> None:
        """Open file dialog to select CSV file and set filename."""
        file_path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")])
        if file_path:
            abs_path = os.path.abspath(file_path)
            self.csv_entry.delete(0, tk.END)
            self.csv_entry.insert(0, abs_path)
            filename = os.path.splitext(os.path.basename(file_path))[0]
            self.filename_entry.delete(0, tk.END)
            self.filename_entry.insert(0, filename)

    def select_dbc(self) -> None:
        """Open file dialog to select DBC file and set filename."""
        file_path = filedialog.askopenfilename(filetypes=[("DBC files", "*.dbc")])
        if file_path:
            abs_path = os.path.abspath(file_path)
            self.dbc_entry.delete(0, tk.END)
            self.dbc_entry.insert(0, abs_path)
            filename = os.path.splitext(os.path.basename(file_path))[0]
            self.filename_entry.delete(0, tk.END)
            self.filename_entry.insert(0, filename)

    def handle_ok(self, root: tk.Tk) -> None:
        """Validate and save configuration on OK button press."""
        filename = self.filename_entry.get().strip()
        blf_path = self.blf_entry.get().strip()
        csv_path = self.csv_entry.get().strip()
        dbc_path = self.dbc_entry.get().strip()

        if not all([filename, blf_path, csv_path, dbc_path]):
            messagebox.showerror("Error", "All fields must be filled.")
            return

        self.check_options = {key: var.get() for key, var in self.check_vars.items()}
        if not self.check_options["auto cut"]:
            start_str = self.start_entry.get().strip().replace(',', '.')
            stop_str = self.stop_entry.get().strip().replace(',', '.')
            if start_str and stop_str:
                try:
                    self.start = float(start_str)
                    self.stop = float(stop_str)
                except ValueError:
                    messagebox.showerror("Error", "Start and Stop must be numbers.")
                    return
            else:
                messagebox.showerror("Error", "Start and Stop must be provided.")
                return
        else:
            self.start = None
            self.stop = None

        if not os.path.exists(blf_path):
            messagebox.showerror("Error", f"Invalid BLF path: {blf_path}")
            return
        if not os.path.exists(csv_path):
            messagebox.showerror("Error", f"Invalid CSV path: {csv_path}")
            return
        if not os.path.exists(dbc_path):
            messagebox.showerror("Error", f"Invalid DBC path: {dbc_path}")
            return

        self.filename = filename
        self.blf_path = blf_path
        self.csv_path = csv_path
        self.dbc_path = dbc_path
        self.save_to_ini()
        self.ok_pressed = True
        root.destroy()

    def handle_cancel(self, root: tk.Tk) -> None:
        """Handle Cancel button press."""
        self.ok_pressed = False
        root.destroy()

    def configure(self) -> bool:
        """Launch configuration GUI and return True if OK pressed with valid inputs."""
        root = tk.Tk()
        root.title("Configure BLF Processing")
        root.configure(bg='lightgray')
        root.geometry("1080x400")

        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TLabel', background='lightgray', font=('Arial', 15))
        style.configure('TEntry', font=('Arial', 15))
        style.configure('ShortTall.TEntry', padding=[5, 10, 5, 10], font=('Arial', 11, 'bold'), fieldbackground=[('white')])
        style.map('ShortTall.TEntry', fieldbackground=[('disabled', 'gray90')])
        style.configure('TButton', font=('Arial', 15))
        style.configure('TCheckbutton', background='lightgray', font=('Arial', 15), indicatorsize=20)
        style.configure('TFrame', background='lightgray')

        main_frame = ttk.Frame(root)
        main_frame.pack(fill=tk.BOTH, expand=True, pady=20)

        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, padx=20, fill=tk.Y, expand=True)

        ttk.Label(left_frame, text="Filename").grid(row=0, column=0, sticky='w', pady=5)
        self.filename_entry = ttk.Entry(left_frame, width=80)
        self.filename_entry.grid(row=0, column=1, pady=5)
        self.filename_entry.insert(0, self.filename)

        ttk.Label(left_frame, text="CAN Log BLF").grid(row=1, column=0, sticky='w', pady=5)
        self.blf_entry = ttk.Entry(left_frame, width=80)
        self.blf_entry.grid(row=1, column=1, pady=5)
        self.blf_entry.insert(0, self.blf_path)
        ttk.Button(left_frame, text="...", width=3, command=self.select_blf).grid(row=1, column=2, pady=5, padx=5)

        ttk.Label(left_frame, text="Travel CSV").grid(row=2, column=0, sticky='w', pady=5)
        self.csv_entry = ttk.Entry(left_frame, width=80)
        self.csv_entry.grid(row=2, column=1, pady=5)
        self.csv_entry.insert(0, self.csv_path)
        ttk.Button(left_frame, text="...", width=3, command=self.select_csv).grid(row=2, column=2, pady=5, padx=5)

        ttk.Label(left_frame, text="CAN Database (DBC)").grid(row=3, column=0, sticky='w', pady=5)
        self.dbc_entry = ttk.Entry(left_frame, width=80)
        self.dbc_entry.grid(row=3, column=1, pady=5)
        self.dbc_entry.insert(0, self.dbc_path)
        ttk.Button(left_frame, text="...", width=3, command=self.select_dbc).grid(row=3, column=2, pady=5, padx=5)

        ttk.Label(left_frame, text="Start [s]").grid(row=4, column=0, sticky='w', pady=5)
        self.start_entry = ttk.Entry(left_frame, width=20, style='ShortTall.TEntry', justify='left')
        self.start_entry.grid(row=4, column=1, pady=8, sticky='w')

        ttk.Label(left_frame, text="Stop [s]").grid(row=5, column=0, sticky='w', pady=5)
        self.stop_entry = ttk.Entry(left_frame, width=20, style='ShortTall.TEntry', justify='left')
        self.stop_entry.grid(row=5, column=1, pady=8, sticky='w')

        button_frame = ttk.Frame(left_frame)
        button_frame.grid(row=6, column=0, columnspan=3, pady=20)
        ttk.Button(button_frame, text="OK", command=lambda: self.handle_ok(root)).pack(side=tk.LEFT, padx=10)
        ttk.Button(button_frame, text="Cancel", command=lambda: self.handle_cancel(root)).pack(side=tk.LEFT)

        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.LEFT, padx=20, fill=tk.Y, expand=True)
        ttk.Label(right_frame, text="Options:").pack(anchor='w', pady=5)
        self.check_vars = {key: tk.BooleanVar(value=value) for key, value in self.check_options.items()}
        for i, key in enumerate(self.check_options):
            ttk.Checkbutton(right_frame, text=key.replace("_", " ").title(), variable=self.check_vars[key]).pack(anchor='w', pady=5)

        def toggle_auto_cut(*args) -> None:
            state = 'disabled' if self.check_vars["auto cut"].get() else 'normal'
            self.start_entry['state'] = state
            self.stop_entry['state'] = state
            if state == 'disabled':
                self.start_entry.delete(0, tk.END)
                self.stop_entry.delete(0, tk.END)
                self.start_entry.insert(0, "Disabled")
                self.stop_entry.insert(0, "Disabled")

        self.check_vars["auto cut"].trace('w', toggle_auto_cut)
        toggle_auto_cut()
        root.mainloop()
        return self.ok_pressed

class LogDealer:
    """Processes BLF logs, extracts segments, merges with CSV, and plots pressure data."""
    def __init__(self, filename: str, blf_path: str, csv_path: str, dbc_path: str,
                 check_options: Dict[str, bool], start: Optional[float], stop: Optional[float]) -> None:
        self.filename: str = filename
        self.blf_path: str = blf_path
        self.csv_path: str = csv_path
        self.dbc_path: str = dbc_path
        self.start: Optional[float] = start
        self.stop: Optional[float] = stop
        self.check_options: Dict[str, bool] = check_options
        self.working_folder: Optional[str] = None
        self.trimmed_blf_path: Optional[Path] = None
        self.active_measurement: Optional[str] = None

    def create_folder(self) -> None:
        """Create a working folder for output files."""
        print("Creating working folder...")
        try:
            dirname = os.path.dirname(self.csv_path)
            folder_name = f"{self.filename}_folder"
            self.working_folder = os.path.join(dirname, folder_name)
            if os.path.exists(self.working_folder):
                shutil.rmtree(self.working_folder)
            os.makedirs(self.working_folder)
            print(f"Folder created: {self.working_folder}")
        except Exception as e:
            print(f"Error creating folder: {e}")
            raise

    def find_brake_press_times_multi(self, df: pd.DataFrame, min_rise_delta: float = 50,
                                     min_relative_rise: float = 0.2, rise_threshold: float = 0.01,
                                     window_size: int = 50, prominence: float = 10,
                                     baseline_window: int = 1000, max_backoff: float = 20,
                                     max_search_window: float = 120.0,
                                     plot_result: bool = True) -> Tuple[Optional[float], Optional[float], List[str], Optional[str]]:
        """
        Detect brake press times by finding significant pressure rises and peak.

        Parameters:
            df: DataFrame with time and pressure columns.
            min_rise_delta: Minimum absolute pressure rise (default: 50 bar).
            min_relative_rise: Minimum relative rise (default: 0.2).
            rise_threshold: Rate of change for rise start (default: 0.01 bar/sample).
            window_size: Rolling window size for smoothing (default: 50).
            prominence: Peak prominence to ignore noise (default: 10).
            baseline_window: Samples for baseline estimation (default: 1000).
            max_backoff: Max allowed pressure drop before peak (default: 20 bar).
            max_search_window: Max time to search for peak after start (default: 120s).
            plot_result: Whether to plot the results (default: True).

        Returns:
            Tuple[float, float, List[str], str]: Start time, end time (peak), rising columns, position.
        """
        print("Detecting brake press times...")
        # Auto-detect time column
        time_cols = [col for col in df.columns if ('time' in col.lower() or 'stamp' in col.lower())
                     and pd.api.types.is_numeric_dtype(df[col])]
        if not time_cols:
            raise ValueError("No time column detected.")
        time_col = time_cols[0]
        if DEBUG:
            print(f"Time column: {time_col}")

        # Make time relative
        df['relative_time'] = df[time_col] - df[time_col].min()

        # Filter pressure columns
        pressure_cols = [col for col in df.select_dtypes(include=[np.number]).columns
                        if ('BrakePressure' in col or col.lower().startswith(('fl', 'fr', 'rl', 'rr')))
                        and col not in [time_col, 'relative_time']]
        if not pressure_cols:
            print("No pressure columns detected.")
            return None, None, [], None
        if DEBUG:
            print(f"Pressure columns: {pressure_cols}")

        # Detect rising columns
        rising_columns = []
        baselines = {}
        for col in tqdm(pressure_cols, desc="Processing columns"):
            col_data = df[col].dropna()
            baseline_samples = col_data.iloc[:min(baseline_window, len(col_data))]
            if len(baseline_samples) == 0:
                continue
            baseline = baseline_samples.mean()
            baselines[col] = baseline

            filled = df[col].ffill().bfill()
            smoothed = filled.rolling(window=window_size, min_periods=1, center=True).mean()
            delta = smoothed.max() - baseline
            relative_delta = delta / (abs(baseline) + 1e-6)

            if DEBUG:
                print(f"  {col}: baseline={baseline:.2f}, delta={delta:.2f}, rel={relative_delta:.2f}")

            if delta < min_rise_delta or relative_delta < min_relative_rise:
                continue

            normalized = smoothed - baseline
            distance = int(max_backoff / (abs(normalized.diff().mean()) + 1e-6)) if normalized.diff().mean() != 0 else 100
            peaks, _ = find_peaks(normalized, height=min_rise_delta, prominence=prominence, distance=distance)
            if len(peaks) > 0:
                rising_columns.append(col)
                if DEBUG:
                    print(f"    Peak at idx {peaks[0]}, height {normalized.iloc[peaks[0]]:.2f}")

        if not rising_columns:
            print("No rising columns detected.")
            return None, None, [], None
        if DEBUG:
            print(f"Rising columns: {rising_columns}")

        # Position logic
        position = None
        positions_set = {col.lower()[:2] for col in rising_columns if not col.lower().startswith('mc')}
        if positions_set == {'fr', 'fl'}:
            position = 'Front axle'
        elif positions_set == {'rl', 'rr'}:
            position = 'Rear axle'
        elif positions_set == {'fr', 'fl', 'rl', 'rr'}:
            position = 'All four wheels'
        elif len(positions_set) == 1:
            position = next(iter(positions_set)).upper()
        if DEBUG:
            print(f"Position: {position}")

        # Aggregate
        normalized_df = pd.DataFrame()
        for col in tqdm(rising_columns, desc="Smoothing rising columns"):
            filled = df[col].ffill().bfill()
            smoothed = filled.rolling(window=window_size, min_periods=1, center=True).mean()
            normalized_df[col] = smoothed - baselines[col]
        agg_normalized = normalized_df.mean(axis=1)
        diff = agg_normalized.diff()

        # Start detection
        rise_starts = np.where(diff > rise_threshold)[0]
        if len(rise_starts) == 0:
            return None, None, rising_columns, position
        start_idx = rise_starts[0]
        start_time_rel = max(0, df['relative_time'].iloc[start_idx] - 1.0)

        # Find true maximum
        max_search_samples = int(max_search_window / (df['relative_time'].diff().mean() + 1e-6))
        search_end_idx = min(start_idx + max_search_samples, len(agg_normalized))
        search_region = agg_normalized.iloc[start_idx:search_end_idx]
        if len(search_region) == 0:
            print("Empty search region after start.")
            return start_time_rel, None, rising_columns, position

        peak_idx = search_region.idxmax()
        end_time_rel = df['relative_time'].iloc[peak_idx]

        # Plot results
        if plot_result:
            plt.figure(figsize=(12, 6))
            colors = ['blue', 'red', 'green', 'orange', 'magenta']
            for i, col in enumerate(rising_columns):
                valid_data = df[[col, 'relative_time']].dropna(subset=[col])
                plt.plot(valid_data['relative_time'], valid_data[col], label=col,
                         color=colors[i % len(colors)], alpha=0.7, linewidth=2)
            plt.axvline(x=start_time_rel, color='green', linestyle='--', label=f'Start ({start_time_rel:.1f}s)')
            plt.axvline(x=end_time_rel, color='red', linestyle='--', label=f'End/Peak ({end_time_rel:.1f}s)')
            plt.xlabel('Time (s)')
            plt.ylabel('Pressure (bar)')
            plt.title(f'Brake Press Detection - {position or "Unknown"}')
            plt.legend()
            plt.grid(True, alpha=0.3)
            output_path = os.path.join(self.working_folder, f"brake_press_{self.filename}.png")
            plt.savefig(output_path, dpi=150, bbox_inches='tight')
            plt.show()
            print(f"Plot saved: {output_path}")

        print(f"Detected: Start={start_time_rel:.2f}s, End={end_time_rel:.2f}s, Position={position}")
        return start_time_rel, end_time_rel, rising_columns, position

    def extract_blf_segment_relative(self, output_path: Optional[str] = None) -> bool:
        """Extract BLF segment by relative time. Returns True if messages written."""
        print("Extracting BLF segment...")
        if not output_path:
            start_str = f"{self.start:.2f}" if self.start is not None else "auto"
            stop_str = f"{self.stop:.2f}" if self.stop is not None else "auto"
            self.trimmed_blf_path = Path(self.working_folder) / f"trimmed_{Path(self.blf_path).stem}_{start_str}s_to_{stop_str}s.blf"

        if self.check_options["auto cut"] and (self.start is None or self.stop is None):
            db = cantools.database.load_file(self.dbc_path) if self.dbc_path else None
            messages = []
            with can.BLFReader(self.blf_path) as log:
                for msg in tqdm(log, desc="Reading BLF for auto-cut"):
                    message_info = {
                        'timestamp': msg.timestamp,
                        'arbitration_id': hex(msg.arbitration_id)
                    }
                    if db:
                        try:
                            message_info.update(db.decode_message(msg.arbitration_id, msg.data))
                        except:
                            pass
                    messages.append(message_info)
            df = pd.DataFrame(messages)
            self.start, self.stop, _, self.active_measurement = self.find_brake_press_times_multi(df)
            if self.start is None or self.stop is None:
                print("Failed to detect brake press times.")
                return False
            print(f"Auto-detected: Start={self.start:.2f}s, End={self.stop:.2f}s")
            self.trimmed_blf_path = Path(self.working_folder) / f"trimmed_{Path(self.blf_path).stem}_{self.start:.2f}s_to_{self.stop:.2f}s.blf"

        try:
            with can.BLFReader(self.blf_path) as reader:
                messages = list(reader)
                if not messages:
                    print("BLF file is empty.")
                    return False
                base_time = messages[0].timestamp
                abs_start_time = base_time + (self.start or 0)
                abs_end_time = base_time + (self.stop or float('inf'))

                messages_written = 0
                with can.BLFWriter(self.trimmed_blf_path) as writer:
                    for message in messages:
                        if abs_start_time <= message.timestamp <= abs_end_time:
                            writer.on_message_received(message)
                            messages_written += 1
                        elif message.timestamp > abs_end_time:
                            break
            print(f"Messages written: {messages_written}")
            return messages_written > 0
        except Exception as e:
            print(f"Error processing BLF: {e}")
            return False

    def rename_csv_columns(self, csv_df: pd.DataFrame, db: cantools.database.Database) -> Optional[pd.DataFrame]:
        """Rename CSV columns based on DBC signals."""
        print("Renaming CSV columns...")
        csv_df.columns = [col.strip() for col in csv_df.columns]
        if len(csv_df.columns) != 2:
            print("Error: CSV must have exactly 2 columns.")
            return None
        if csv_df.columns[1].lower() != 'travel':
            print(f"Error: Second column must be 'travel', got '{csv_df.columns[1]}'.")
            return None

        all_signals = {signal.name.lower(): signal.name for message in db.messages for signal in message.signals}
        first_col = csv_df.columns[0].lower()
        cyrillic_to_latin = {'м': 'm', 'с': 'c', 'р': 'r', 'л': 'l', 'ф': 'f'}
        first_col_normalized = first_col
        for cyr, lat in cyrillic_to_latin.items():
            first_col_normalized = first_col_normalized.replace(cyr, lat)

        valid_prefixes = ['mc', 'rr', 'rl', 'fl', 'fr', 'front', 'rear']
        if first_col_normalized in all_signals:
            return csv_df
        if first_col_normalized not in valid_prefixes:
            print(f"Error: Invalid prefix '{first_col_normalized}'. Valid: {valid_prefixes}")
            return None

        column_mapping = {}
        if first_col_normalized in ['front', 'rear']:
            mc_signals = [sig for sig in all_signals.keys() if sig.startswith('mc')]
            if not mc_signals:
                print("Error: No MC signals in DBC.")
                return None
            column_mapping[first_col] = all_signals[mc_signals[0]]
        else:
            matching_signals = [sig for sig in all_signals.keys() if sig.startswith(first_col_normalized)]
            if not matching_signals:
                print(f"Error: No signals start with '{first_col_normalized}'.")
                return None
            column_mapping[first_col] = all_signals[matching_signals[0]]
        return csv_df.rename(columns=column_mapping)

    def load_csv_pathlib(self, file_path: str) -> str:
        """Load CSV content with pathlib."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File '{file_path}' not found.")
        if not path.is_file():
            raise ValueError(f"'{file_path}' is not a file.")
        if path.stat().st_size == 0:
            raise ValueError(f"File '{file_path}' is empty.")
        return path.read_text(encoding='utf-8')

    def validate_and_load_csv(self, csv_content: str, threshold: float = 0.1) -> Optional[pd.DataFrame]:
        """Validate and load CSV into DataFrame."""
        print("Validating CSV content...")
        lines = csv_content.strip().split('\n')
        if len(lines) < 2:
            print("Error: CSV must have header and data.")
            return None

        header = lines[0].strip()
        if header.count(';') != 1:
            print(f"Error: Header must have one semicolon, found {header.count(';')}.")
            return None
        columns = [col.strip() for col in header.split(';')]
        if len(columns) != 2:
            print(f"Error: Expected 2 columns, found {len(columns)}.")
            return None

        data = []
        for i, line in enumerate(lines[1:], start=2):
            if line.count(';') != 1:
                if DEBUG:
                    print(f"Error in line {i}: Expected one semicolon, found {line.count(';')}.")
                continue
            values = [val.strip().replace(',', '.') for val in line.split(';')]
            if len(values) != 2:
                if DEBUG:
                    print(f"Error in line {i}: Expected 2 values, found {len(values)}.")
                continue
            try:
                data.append([float(val) for val in values])
            except ValueError:
                if DEBUG:
                    print(f"Error in line {i}: Could not convert to float: {values}")
                continue

        if not data:
            print("Error: No valid data rows.")
            return None

        df = pd.DataFrame(data, columns=columns)
        for col in df.columns:
            max_val = df[col].abs().max()
            if max_val == 0:
                continue
            threshold_val = threshold * max_val
            diffs = df[col].diff().abs()
            sharp_changes = diffs[diffs > threshold_val]
            if DEBUG:
                for idx in sharp_changes.index:
                    print(f"Warning in '{col}' at row {idx + 2}: Sharp change {diffs[idx]:.2f} > {threshold_val:.2f}.")
        return df

    def merge_with(self, csv_df: pd.DataFrame, other_df: pd.DataFrame) -> pd.DataFrame:
        """Merge CSV DataFrame with BLF DataFrame by matching closest key."""
        print("Merging CSV with BLF data...")
        if csv_df.shape[1] != 2:
            raise ValueError("CSV must have exactly 2 columns.")
        key_col, value_col = csv_df.columns
        if key_col not in other_df.columns:
            raise ValueError(f"BLF DataFrame must have column '{key_col}'.")
        other_df[value_col] = np.nan
        for _, row in csv_df.iterrows():
            diffs = np.abs(other_df[key_col] - row[key_col])
            closest_idx = diffs.idxmin()
            other_df.at[closest_idx, value_col] = row[value_col]
        return other_df

    def plot_pressure_vs_time(self, df: pd.DataFrame, graph_title: str) -> None:
        """Plot pressure vs. time with calibration option."""
        print("Plotting pressure vs. time...")
        pressure_columns = PRESSURE_COLUMNS
        df = df[['timestamp'] + [col for col in pressure_columns if col in df.columns]].copy()
        df['timestamp'] -= df['timestamp'].min()

        if self.check_options["first msg calib"]:
            print("Applying zero calibration...")
            calibration_values = df[pressure_columns].iloc[0]
            if DEBUG:
                print("Calibration values:", calibration_values.to_dict())
            df[pressure_columns] = df[pressure_columns] - calibration_values

        plt.figure(figsize=(14, 8))
        colors = ['blue', 'red', 'green', 'orange', 'magenta']
        line_styles = ['-', '--', '-.', ':', '-']
        labels = ['FL Pressure', 'FR Pressure', 'RL Pressure', 'RR Pressure', 'MC Pressure']
        for i, col in enumerate(pressure_columns):
            if col in df.columns:
                valid_data = df[[col, 'timestamp']].dropna(subset=[col])
                plt.plot(valid_data['timestamp'], valid_data[col], label=labels[i], linewidth=2,
                         color=colors[i], linestyle=line_styles[i])

        plt.xlabel('Time (s)', fontsize=14, fontweight='bold')
        plt.ylabel('Pressure (bar)', fontsize=14, fontweight='bold')
        plt.title(graph_title or 'Pressure vs. Time', fontsize=16, fontweight='bold')
        plt.legend(fontsize=12)
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        output_path = os.path.join(self.working_folder, f"pressure_vs_time_{self.filename}.png")
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.show()
        print(f"Plot saved: {output_path}")
        if SAVE_MORE:
            output_csv = os.path.join(self.working_folder, f"{self.filename}_pressure.csv")
            df.to_csv(output_csv, index=False, encoding='utf-8')
            print(f"Data saved: {output_csv}")

    def plot_pressure_vs_travel(self, df: pd.DataFrame, graph_title: str) -> None:
        """Plot pressure vs. travel with interpolation and calibration."""
        print("Plotting pressure vs. travel...")
        pressure_columns = PRESSURE_COLUMNS
        if 'travel' not in df.columns:
            print("Error: 'travel' column not found in DataFrame.")
            return
        df = df[['travel'] + [col for col in pressure_columns if col in df.columns]].copy()
        df = df.dropna(subset=['travel']).sort_values(by='travel')

        if self.check_options["first msg calib"]:
            print("Applying zero calibration for pressure vs. travel...")
            calibration_values = df[pressure_columns].iloc[0]
            if DEBUG:
                print("Calibration values:", calibration_values.to_dict())
            df[pressure_columns] = df[pressure_columns] - calibration_values

        plt.figure(figsize=(14, 8))
        colors = ['blue', 'red', 'green', 'orange', 'magenta']
        line_styles = ['-', '--', '-.', ':', '-']
        labels = ['FL Pressure', 'FR Pressure', 'RL Pressure', 'RR Pressure', 'MC Pressure']
        for i, col in enumerate(pressure_columns):
            if col in df.columns:
                valid_data = df[['travel', col]].dropna(subset=[col])
                if len(valid_data) < 2:
                    print(f"Warning: Insufficient data for {col} in pressure vs. travel plot.")
                    continue
                # Interpolate for smoother curves
                x = valid_data['travel']
                y = valid_data[col]
                if len(x) > 3:  # Need enough points for spline
                    f = interpolate.interp1d(x, y, kind='cubic', fill_value="extrapolate")
                    x_smooth = np.linspace(x.min(), x.max(), 300)
                    y_smooth = f(x_smooth)
                    plt.plot(x_smooth, y_smooth, label=labels[i], linewidth=2,
                             color=colors[i], linestyle=line_styles[i])
                else:
                    plt.plot(x, y, label=labels[i], linewidth=2,
                             color=colors[i], linestyle=line_styles[i])

        plt.xlabel('Travel (mm)', fontsize=14, fontweight='bold')
        plt.ylabel('Pressure (bar)', fontsize=14, fontweight='bold')
        plt.title(graph_title or 'Pressure vs. Travel', fontsize=16, fontweight='bold')
        plt.legend(fontsize=12)
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        output_path = os.path.join(self.working_folder, f"pressure_vs_travel_{self.filename}.png")
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.show()
        print(f"Plot saved: {output_path}")
        output_csv = os.path.join(self.working_folder, f"{self.filename}_pressure_travel_minimal.csv")
        df.to_csv(output_csv, index=False, encoding='utf-8')
        print(f"Data saved: {output_csv}")

    def load_files(self) -> None:
        """Load and process BLF and CSV files, merge, and plot."""
        print("Loading and processing files...")
        try:
            csv_data = self.load_csv_pathlib(self.csv_path)
            db = cantools.database.load_file(self.dbc_path)
            csv_df = self.validate_and_load_csv(csv_data)
            if csv_df is None:
                raise ValueError("Failed to validate CSV.")
            csv_df = self.rename_csv_columns(csv_df, db)
            if csv_df is None:
                raise ValueError("Failed to rename CSV columns.")
            if DEBUG:
                print("CSV columns:", csv_df.columns.tolist())
                print(csv_df.head(10))

            blf_path = self.trimmed_blf_path if self.check_options["auto cut"] and self.trimmed_blf_path else self.blf_path
            with can.BLFReader(blf_path) as log:
                all_signals = sorted({signal.name for message in db.messages for signal in message.signals})
                columns = ['timestamp', 'arbitration_id'] + all_signals
                data_rows = []
                message_info = {message.frame_id: message.name for message in db.messages}
                for msg in tqdm(log, desc="Processing CAN messages"):
                    row_data = {'timestamp': msg.timestamp, 'arbitration_id': msg.arbitration_id}
                    for signal in all_signals:
                        row_data[signal] = None
                    try:
                        decoded = db.decode_message(msg.arbitration_id, msg.data)
                        row_data.update(decoded)
                    except cantools.database.DecodeError:
                        pass
                    data_rows.append(row_data)

                df = pd.DataFrame(data_rows, columns=columns)
                df = df.ffill().dropna(subset=['timestamp'])
                df = df[df['arbitration_id'] != df['arbitration_id'].iloc[0]]
                df = df.drop(columns=['arbitration_id'] + [col for col in ['Current_a_6', 'a_7', 'vacuum_sensor_a0'] if col in df.columns])
                merged_df = self.merge_with(csv_df, df)


                #  and not self.check_options["auto cut"]:

                print(f"{self.start = }, {self.stop = } {self.check_options["auto cut"] = }")
                if self.check_options["auto cut"] is False:
                    # Manual mode: plot lines without detection
                    plt.figure(figsize=(12, 6))
                    colors = ['blue', 'red', 'green', 'orange', 'magenta']
                    pressure_columns = ['FL_BrakePressure_a1', 'FR_BrakePressure_a2', 'RL_BrakePressure_a3', 'RR_BrakePressure_a4', 'MC2_BrakePressure_a5']
                    df['relative_time'] = df['timestamp'] - df['timestamp'].min()  # if not already
                    for i, col in enumerate(pressure_columns):
                        if col in df.columns:
                            valid_data = df[[col, 'relative_time']].dropna(subset=[col])
                            plt.plot(valid_data['relative_time'], valid_data[col], label=col, color=colors[i % len(colors)], alpha=0.7, linewidth=2)
                    plt.axvline(x=self.start, color='green', linestyle='--', label=f'Start ({self.start:.1f}s)')
                    plt.axvline(x=self.stop, color='red', linestyle='--', label=f'End ({self.stop:.1f}s)')
                    plt.xlabel('Time (s)')
                    plt.ylabel('Pressure (bar)')
                    plt.title(f'Manual Brake Segment - Start={self.start:.1f}s, End={self.stop:.1f}s')
                    plt.legend()
                    plt.grid(True, alpha=0.3)
                    output_path = os.path.join(self.working_folder, f"manual_brake_segment_{self.filename}.png")
                    if SAVE_MORE:
                        plt.savefig(output_path, dpi=150, bbox_inches='tight')
                    plt.show()
                    print(f"Manual plot saved: {output_path}")
                else:
                    # Auto mode: use detection
                    self.find_brake_press_times_multi(merged_df, plot_result=True)

                output_csv = os.path.join(self.working_folder, f"{self.filename}pressure_with_travel.csv")
                merged_df.to_csv(output_csv, index=False, encoding='utf-8')
                print(f"Merged data saved: {output_csv}")

                graph_title = self.active_measurement or simpledialog.askstring(
                    "Graph Title", "Enter graph title (default: Pressure vs. Time/Travel):",
                    initialvalue="Pressure vs. Time/Travel"
                ) or "Pressure vs. Time/Travel"

                if self.check_options["Pressure-time graph"]:
                    self.plot_pressure_vs_time(merged_df, graph_title)
                if self.check_options["All pressures graph"]:
                    self.plot_pressure_vs_travel(merged_df, graph_title)
                print("Processing completed successfully.")
        except Exception as e:
            print(f"Error processing files: {e}")
            raise

def main() -> None:
    """Main entry point for BLF processing."""
    config = BLFConfigurator()
    if config.configure():
        dealer = LogDealer(config.filename, config.blf_path, config.csv_path, config.dbc_path,
                          config.check_options, config.start, config.stop)
        dealer.create_folder()
        if config.check_options["auto cut"]:
            dealer.extract_blf_segment_relative()
        dealer.load_files()

if __name__ == "__main__":
    main()
