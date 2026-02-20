import math
import threading
import tkinter as tk
from dataclasses import dataclass
from typing import Optional

import numpy as np
import soundcard as sc


UI_REFRESH_MS = 80
AUDIO_BLOCK_FRAMES = 2048
ACTIVE_THRESHOLD = 0.015
SMOOTHING = 0.28


@dataclass
class DirectionState:
    azimuth: float = 0.0
    confidence: float = 0.0
    level: float = 0.0
    active: bool = False


class AudioDirectionEstimator:
    """Estimate left-right source direction from loopback stereo output."""

    def __init__(self) -> None:
        self._state = DirectionState()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def snapshot(self) -> DirectionState:
        with self._lock:
            return DirectionState(**self._state.__dict__)

    def _worker(self) -> None:
        speaker = sc.default_speaker()
        loopback = sc.get_microphone(speaker.id, include_loopback=True)
        smoothed_pan = 0.0
        smoothed_level = 0.0

        with loopback.recorder(samplerate=48000, channels=2, blocksize=AUDIO_BLOCK_FRAMES) as rec:
            while not self._stop_event.is_set():
                data = rec.record(numframes=AUDIO_BLOCK_FRAMES)
                if data.shape[1] < 2:
                    continue

                left = np.sqrt(np.mean(np.square(data[:, 0])))
                right = np.sqrt(np.mean(np.square(data[:, 1])))
                level = float((left + right) * 0.5)
                pan = float((right - left) / max(left + right, 1e-9))

                smoothed_pan = (SMOOTHING * pan) + ((1.0 - SMOOTHING) * smoothed_pan)
                smoothed_level = (SMOOTHING * level) + ((1.0 - SMOOTHING) * smoothed_level)

                active = smoothed_level >= ACTIVE_THRESHOLD
                azimuth = float(np.clip(smoothed_pan, -1.0, 1.0) * 90.0)
                confidence = float(min(abs(smoothed_pan), 1.0))

                with self._lock:
                    self._state.azimuth = azimuth
                    self._state.confidence = confidence
                    self._state.level = smoothed_level
                    self._state.active = active


class Overlay:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.93)
        self.root.configure(bg="#0a1017")
        self.root.geometry("320x420+70+70")

        self.title_label = tk.Label(
            self.root,
            text="声音方位罗盘 (立体声估算)",
            bg="#0a1017",
            fg="#73f5b0",
            font=("Microsoft YaHei UI", 11, "bold"),
            pady=8,
        )
        self.title_label.pack()

        self.canvas = tk.Canvas(
            self.root,
            width=260,
            height=260,
            bg="#0f1a24",
            highlightthickness=0,
        )
        self.canvas.pack(padx=16, pady=4)

        self.info_label = tk.Label(
            self.root,
            text="等待音频...",
            bg="#0a1017",
            fg="#d3e7ff",
            font=("Microsoft YaHei UI", 10),
            justify="left",
        )
        self.info_label.pack(pady=6)

        self.exit_button = tk.Button(
            self.root,
            text="退出",
            command=self.close,
            bg="#1b2a38",
            fg="#d8eaff",
            activebackground="#284156",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            padx=12,
            pady=4,
        )
        self.exit_button.pack(pady=(0, 8))

        # Fit window size to actual widget requirements (prevents clipping on high-DPI displays).
        self.root.update_idletasks()
        req_w = max(320, self.root.winfo_reqwidth())
        req_h = max(420, self.root.winfo_reqheight())
        self.root.geometry(f"{req_w}x{req_h}+70+70")

        self._draw_compass_base()
        self._arrow = None

        self.estimator = AudioDirectionEstimator()
        self.estimator.start()

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Escape>", lambda _e: self.close())

    def _draw_compass_base(self) -> None:
        c = self.canvas
        c.delete("all")
        c.create_oval(20, 20, 240, 240, outline="#2d4a64", width=2)
        c.create_oval(50, 50, 210, 210, outline="#193246", width=1)
        c.create_line(130, 20, 130, 240, fill="#1e3648")
        c.create_line(20, 130, 240, 130, fill="#1e3648")

        c.create_text(130, 10, text="前方 0°", fill="#8fb6d8", font=("Microsoft YaHei UI", 9))
        c.create_text(12, 130, text="左 -90°", fill="#8fb6d8", anchor="w", font=("Microsoft YaHei UI", 9))
        c.create_text(248, 130, text="右 +90°", fill="#8fb6d8", anchor="e", font=("Microsoft YaHei UI", 9))
        c.create_text(130, 250, text="后方* 不可判定", fill="#6d8ba8", font=("Microsoft YaHei UI", 8))

    def _draw_arrow(self, azimuth: float, active: bool, confidence: float) -> None:
        if self._arrow is not None:
            self.canvas.delete(self._arrow)

        cx, cy, radius = 130.0, 130.0, 90.0
        rad = math.radians(azimuth)
        tx = cx + (radius * math.sin(rad))
        ty = cy - (radius * math.cos(rad))

        color = "#f7d16d" if active else "#6e7f90"
        width = 5 if confidence > 0.2 else 3
        self._arrow = self.canvas.create_line(
            cx,
            cy,
            tx,
            ty,
            fill=color,
            width=width,
            arrow=tk.LAST,
            arrowshape=(14, 16, 6),
        )

    def tick(self) -> None:
        state = self.estimator.snapshot()

        if not state.active:
            self.info_label.config(text="未检测到明显定向音\n请确保是立体声输出")
        else:
            if state.azimuth > 10:
                direction = "前方偏右"
            elif state.azimuth < -10:
                direction = "前方偏左"
            else:
                direction = "正前方附近"

            self.info_label.config(
                text=(
                    f"方位估计: {direction}\n"
                    f"角度: {state.azimuth:+.1f}°  强度: {state.level:.3f}"
                )
            )

        self._draw_arrow(state.azimuth, state.active, state.confidence)
        self.root.after(UI_REFRESH_MS, self.tick)

    def close(self) -> None:
        self.estimator.stop()
        self.root.destroy()

    def run(self) -> None:
        self.tick()
        self.root.mainloop()


if __name__ == "__main__":
    Overlay().run()
