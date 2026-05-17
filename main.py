# main.py
# Oromusix - Android 11+ safer Kivy Music Player
# Works in Pydroid 3 and is lightweight for APK/MT Manager testing.

import os
import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.core.window import Window
from kivy.storage.jsonstore import JsonStore

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.slider import Slider
from kivy.uix.scrollview import ScrollView
from kivy.graphics import Color, RoundedRectangle


Window.clearcolor = (0.005, 0.018, 0.045, 1)


# Android 11+ safer: scan only these public media folders.
MUSIC_FOLDERS = [
    "/storage/emulated/0/Music",
    "/storage/emulated/0/Download",
]

AUDIO_EXTENSIONS = (".mp3", ".wav", ".ogg", ".m4a")

IGNORE_KEYWORDS = [
    "whatsapp",
    "voice notes",
    "voicenotes",
    "recordings",
    "telegram",
    "cache",
    "sent",
    "status",
]


def request_android_permissions():
    """
    Requests storage permissions on Android.
    In Pydroid/non-APK mode this may fail silently, which is safe.
    """
    try:
        from android.permissions import request_permissions, Permission

        request_permissions([
            Permission.READ_EXTERNAL_STORAGE,
            Permission.WRITE_EXTERNAL_STORAGE,
        ])

    except Exception:
        pass


class SafeAudioPlayer:
    """
    Safe wrapper for Kivy SoundLoader.

    Android backends may not support pause() or seek().
    This class prevents crashes by safely falling back to stop().
    """

    def __init__(self):
        self.sound = None
        self.path = None
        self.playing = False

    def load(self, path):
        self.stop()
        self.path = path

        try:
            self.sound = SoundLoader.load(path)
            return self.sound is not None
        except Exception:
            self.sound = None
            return False

    def play(self):
        if not self.sound:
            return False

        try:
            self.sound.play()
            self.playing = True
            return True
        except Exception:
            self.playing = False
            return False

    def pause(self):
        if not self.sound:
            return False

        try:
            if hasattr(self.sound, "pause") and callable(self.sound.pause):
                self.sound.pause()
            else:
                self.sound.stop()

            self.playing = False
            return True

        except Exception:
            try:
                self.sound.stop()
            except Exception:
                pass

            self.playing = False
            return False

    def stop(self):
        if self.sound:
            try:
                self.sound.stop()
            except Exception:
                pass

        self.playing = False

    def seek(self, seconds):
        if not self.sound:
            return False

        try:
            if hasattr(self.sound, "seek") and callable(self.sound.seek):
                self.sound.seek(seconds)
                return True
        except Exception:
            return False

        return False

    def position(self):
        if not self.sound:
            return 0

        try:
            return max(0, self.sound.get_pos())
        except Exception:
            return 0

    def length(self):
        if not self.sound:
            return 0

        try:
            return max(0, self.sound.length or 0)
        except Exception:
            return 0


class Card(BoxLayout):
    """Lightweight premium rounded card."""

    def __init__(self, bg=(0.025, 0.105, 0.19, 1), **kwargs):
        super().__init__(**kwargs)
        self.padding = 16
        self.spacing = 12

        with self.canvas.before:
            Color(*bg)
            self.bg_rect = RoundedRectangle(
                radius=[26],
                pos=self.pos,
                size=self.size
            )

        self.bind(pos=self.update_bg, size=self.update_bg)

    def update_bg(self, *args):
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size


class OromusixApp(App):

    def build(self):
        self.title = "Oromusix"

        request_android_permissions()

        self.player = SafeAudioPlayer()
        self.store = JsonStore("oromusix_favorites.json")

        self.playlist = []
        self.current_index = 0
        self.user_dragging_slider = False
        self.auto_next_lock = False

        self.root = BoxLayout(
            orientation="vertical",
            padding=16,
            spacing=14
        )

        self.build_ui()

        Clock.schedule_once(lambda dt: self.start_scan(), 1)
        Clock.schedule_interval(self.update_ui, 0.5)

        return self.root

    # ---------------- UI ----------------
    def build_ui(self):
        header = Label(
            text="[b]OROMUSIX[/b]\n[size=15]Premium Oromo Music Player[/size]",
            markup=True,
            font_size=34,
            color=(0.25, 0.72, 1, 1),
            size_hint=(1, 0.13),
            halign="center"
        )
        self.root.add_widget(header)

        player_card = Card(
            orientation="vertical",
            size_hint=(1, 0.33)
        )

        self.song_title = Label(
            text="[b]Scanning Music & Download folders...[/b]",
            markup=True,
            font_size=22,
            color=(1, 1, 1, 1),
            halign="center"
        )
        player_card.add_widget(self.song_title)

        self.song_path = Label(
            text="Searching only Music and Download for Android 11+ safety.",
            markup=True,
            font_size=13,
            color=(0.68, 0.86, 1, 1),
            halign="center"
        )
        player_card.add_widget(self.song_path)

        self.slider = Slider(
            min=0,
            max=100,
            value=0
        )
        self.slider.bind(
            on_touch_down=self.on_slider_touch_down,
            on_touch_up=self.on_slider_touch_up
        )
        player_card.add_widget(self.slider)

        self.time_label = Label(
            text="00:00 / 00:00",
            font_size=15,
            color=(0.82, 0.92, 1, 1)
        )
        player_card.add_widget(self.time_label)

        self.root.add_widget(player_card)

        controls = BoxLayout(
            orientation="horizontal",
            spacing=8,
            size_hint=(1, 0.12)
        )

        self.prev_btn = self.make_button("◀◀")
        self.play_btn = self.make_button("▶")
        self.pause_btn = self.make_button("⏸")
        self.stop_btn = self.make_button("⏹")
        self.next_btn = self.make_button("▶▶")
        self.fav_btn = self.make_button("♡")

        self.prev_btn.bind(on_press=self.previous_song)
        self.play_btn.bind(on_press=self.play_song)
        self.pause_btn.bind(on_press=self.pause_song)
        self.stop_btn.bind(on_press=self.stop_song)
        self.next_btn.bind(on_press=self.next_song)
        self.fav_btn.bind(on_press=self.toggle_favorite)

        for button in [
            self.prev_btn,
            self.play_btn,
            self.pause_btn,
            self.stop_btn,
            self.next_btn,
            self.fav_btn
        ]:
            controls.add_widget(button)

        self.root.add_widget(controls)

        lyrics_card = Card(
            orientation="vertical",
            size_hint=(1, 0.34)
        )

        lyrics_title = Label(
            text="[b]Lyrics[/b]",
            markup=True,
            font_size=20,
            color=(0.25, 0.72, 1, 1),
            size_hint=(1, 0.16)
        )
        lyrics_card.add_widget(lyrics_title)

        scroll = ScrollView(size_hint=(1, 0.84))

        self.lyrics_label = Label(
            text="Lyrics will appear here.",
            markup=True,
            font_size=18,
            color=(0.93, 0.97, 1, 1),
            halign="center",
            valign="top",
            size_hint_y=None
        )

        self.lyrics_label.bind(
            width=lambda instance, value: setattr(instance, "text_size", (value, None)),
            texture_size=lambda instance, value: setattr(instance, "height", value[1] + 40)
        )

        scroll.add_widget(self.lyrics_label)
        lyrics_card.add_widget(scroll)

        self.root.add_widget(lyrics_card)

        self.status = Label(
            text="Starting...",
            markup=True,
            font_size=14,
            color=(0.70, 0.84, 0.96, 1),
            size_hint=(1, 0.08)
        )
        self.root.add_widget(self.status)

    def make_button(self, text):
        return Button(
            text=text,
            font_size=19,
            background_color=(0.02, 0.24, 0.48, 1),
            color=(1, 1, 1, 1)
        )

    # ---------------- Scanner ----------------
    def start_scan(self):
        self.status.text = "Scanning Music and Download folders..."
        thread = threading.Thread(target=self.scan_music, daemon=True)
        thread.start()

    def scan_music(self):
        """
        Android 11+ safer scanner.

        It only scans:
        - /storage/emulated/0/Music
        - /storage/emulated/0/Download

        Any blocked folder or unreadable file is skipped safely.
        """
        songs = []

        for folder in MUSIC_FOLDERS:
            if not os.path.exists(folder):
                continue

            try:
                for current_root, dirs, files in os.walk(folder, topdown=True):

                    try:
                        dirs[:] = [
                            d for d in dirs
                            if not d.startswith(".")
                            and not self.should_ignore(os.path.join(current_root, d))
                        ]
                    except Exception:
                        dirs[:] = []

                    if self.should_ignore(current_root):
                        continue

                    for file_name in files:
                        try:
                            if file_name.startswith("."):
                                continue

                            if not file_name.lower().endswith(AUDIO_EXTENSIONS):
                                continue

                            path = os.path.join(current_root, file_name)

                            if self.should_ignore(path):
                                continue

                            if os.path.isfile(path):
                                songs.append(path)

                        except Exception:
                            continue

            except Exception:
                continue

        songs = sorted(
            list(set(songs)),
            key=lambda x: os.path.basename(x).lower()
        )

        Clock.schedule_once(lambda dt: self.finish_scan(songs), 0)

    def should_ignore(self, path):
        try:
            lower = path.lower()
            return any(word in lower for word in IGNORE_KEYWORDS)
        except Exception:
            return True

    def finish_scan(self, songs):
        self.playlist = songs

        if not self.playlist:
            self.song_title.text = "[b]No songs found[/b]"
            self.song_path.text = "Put MP3 files in Music or Download folder."
            self.status.text = "No playable music found."
            return

        self.current_index = 0
        self.load_current_song(autoplay=False)
        self.status.text = f"Found {len(self.playlist)} songs."

    # ---------------- Player ----------------
    def load_current_song(self, autoplay=False):
        if not self.playlist:
            return

        self.current_index = self.current_index % len(self.playlist)
        path = self.playlist[self.current_index]

        ok = self.player.load(path)

        if not ok:
            self.status.text = "Unsupported file skipped."
            self.next_song(None)
            return

        title = os.path.basename(path)

        self.song_title.text = f"[b]{title}[/b]"
        self.song_path.text = path
        self.slider.value = 0
        self.time_label.text = "00:00 / 00:00"

        self.update_favorite_button()
        self.update_lyrics(title)

        if autoplay:
            Clock.schedule_once(lambda dt: self.play_song(None), 0.2)

    def play_song(self, instance):
        if not self.player.sound:
            self.status.text = "No song loaded."
            return

        if self.player.play():
            self.status.text = "Playing..."
        else:
            self.status.text = "Could not play this file."

    def pause_song(self, instance):
        if self.player.pause():
            self.status.text = "Paused."
        else:
            self.status.text = "Pause unsupported. Playback stopped safely."

    def stop_song(self, instance):
        self.player.stop()
        self.slider.value = 0
        self.time_label.text = "00:00 / 00:00"
        self.status.text = "Stopped."

    def next_song(self, instance):
        if not self.playlist:
            return

        self.current_index = (self.current_index + 1) % len(self.playlist)
        self.load_current_song(autoplay=True)

    def previous_song(self, instance):
        if not self.playlist:
            return

        self.current_index = (self.current_index - 1) % len(self.playlist)
        self.load_current_song(autoplay=True)

    # ---------------- Slider ----------------
    def on_slider_touch_down(self, instance, touch):
        if instance.collide_point(*touch.pos):
            self.user_dragging_slider = True
        return False

    def on_slider_touch_up(self, instance, touch):
        if instance.collide_point(*touch.pos):
            self.user_dragging_slider = False

            length = self.player.length()

            if length > 0:
                target = (instance.value / 100) * length
                ok = self.player.seek(target)

                if not ok:
                    self.status.text = "Seek unsupported on this Android audio backend."

        return False

    # ---------------- UI updater ----------------
    def update_ui(self, dt):
        if not self.player.sound:
            return

        pos = self.player.position()
        length = self.player.length()

        if length > 0:
            if not self.user_dragging_slider:
                self.slider.value = (pos / length) * 100

            self.time_label.text = (
                f"{self.format_time(pos)} / {self.format_time(length)}"
            )

            if self.player.playing and pos >= length - 0.7:
                if not self.auto_next_lock:
                    self.auto_next_lock = True
                    self.next_song(None)
                    Clock.schedule_once(self.unlock_auto_next, 1.5)

    def unlock_auto_next(self, dt):
        self.auto_next_lock = False

    @staticmethod
    def format_time(seconds):
        seconds = int(seconds or 0)
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    # ---------------- Favorites ----------------
    def toggle_favorite(self, instance):
        if not self.playlist:
            return

        path = self.playlist[self.current_index]

        if self.store.exists(path):
            self.store.delete(path)
            self.status.text = "Removed from favorites."
        else:
            self.store.put(
                path,
                title=os.path.basename(path),
                path=path
            )
            self.status.text = "Added to favorites."

        self.update_favorite_button()

    def update_favorite_button(self):
        if not self.playlist:
            self.fav_btn.text = "♡"
            return

        path = self.playlist[self.current_index]
        self.fav_btn.text = "❤️" if self.store.exists(path) else "♡"

    # ---------------- Lyrics ----------------
    def update_lyrics(self, title):
        clean = title.rsplit(".", 1)[0].replace("_", " ")

        self.lyrics_label.text = (
            f"[b]{clean}[/b]\n\n"
            "Lyrics not added yet.\n\n"
            "Future Oromusix upgrade:\n"
            "• synced LRC lyrics\n"
            "• Oromo lyrics database\n"
            "• offline favorites playlist\n\n"
            "🎵 Enjoy Oromusix."
        )


if __name__ == "__main__":
    OromusixApp().run()