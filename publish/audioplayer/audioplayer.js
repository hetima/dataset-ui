/* AudioPlayer / AudioPlayerControl — シンプル軽量オーディオプレイヤー */
(function (root) {
  'use strict';

  /* ── ユーティリティ ── */

  function formatTime(seconds) {
    if (!Number.isFinite(seconds) || seconds < 0) return '00:00';
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
  }

  function clamp(v, min, max) {
    return Math.max(min, Math.min(max, v));
  }

  /* ── AudioPlayerControl（UI なし、同時再生防止のみ） ── */

  class AudioPlayerControl {
    /**
     * @param {{ id?: string, volume?: number }} options
     */
    constructor(options = {}) {
      this.id = options.id || ('audio_player_control_' + Math.random().toString(36).slice(2));
      this.volume = clamp(options.volume != null ? options.volume : 1, 0, 1);
      /** @type {Set<AudioPlayer>} */
      this.players = new Set();
      AudioPlayerControl._controls.set(this.id, this);
    }

    /**
     * 既存のコントロールを返す。なければ新規作成する。
     * @param {string} [id]
     * @param {object} [options]
     */
    static get(id, options) {
      id = id || 'default';
      if (!AudioPlayerControl._controls.has(id)) {
        new AudioPlayerControl({ ...options, id });
      }
      return AudioPlayerControl._controls.get(id);
    }

    /** @param {AudioPlayer} player */
    register(player) {
      this.players.add(player);
      player._applyVolume(this.volume);
    }

    /** @param {AudioPlayer} player */
    unregister(player) {
      this.players.delete(player);
    }

    /**
     * 再生開始を通知し、他のプレイヤーを一時停止する。
     * @param {AudioPlayer} player
     */
    notifyPlay(player) {
      this.players.forEach(function (p) {
        if (p !== player) p.pause();
      });
    }

    /**
     * 音量を全プレイヤーに反映する。
     * @param {number} value 0〜1
     */
    setVolume(value) {
      this.volume = clamp(value, 0, 1);
      this.players.forEach(function (p) {
        p._applyVolume(value);
      });
    }
  }

  AudioPlayerControl._controls = new Map();

  /* ── AudioPlayer ── */

  class AudioPlayer {
    /**
     * @param {HTMLElement|string} target
     * @param {{
     *   id?: string,
     *   name?: string,
     *   control?: string,
     *   autoplay?: boolean,
     * }} options
     */
    constructor(target, options) {
      options = options || {};
      this.root = typeof target === 'string'
        ? document.getElementById(target)
        : target;
      this.id = options.id || (this.root && this.root.id) || ('audioplayer_' + Math.random().toString(36).slice(2));
      this.name = options.name || this.id;
      this.autoplay = !!options.autoplay;
      this.destroyed = false;
      this._seeking = false;

      /* DOM 要素 */
      this.audio = null;
      this.playBtn = null;
      this.seekSlider = null;
      this.timeDisplay = null;
      this.muteBtn = null;
      this.volumeSlider = null;

      this._build();
      this._bind();

      this.control = AudioPlayerControl.get(options.control || 'default');
      this.control.register(this);

      AudioPlayer._players.set(this.name, this);
    }

    /**
     * 登録済みプレイヤーを name で取得する。
     * @param {string} name
     * @returns {AudioPlayer|null}
     */
    static get(name) {
      return AudioPlayer._players.get(name) || null;
    }

    /**
     * 登録済みプレイヤーを破棄する。
     * @param {string} name
     */
    static destroy(name) {
      const p = AudioPlayer._players.get(name);
      if (p) p.destroy();
    }

    /* ── DOM 構築 ── */
    _build() {
      const root = this.root;
      root.classList.add('audio-player');

      const audio = document.createElement('audio');
      audio.className = 'audio-player__audio';
      audio.preload = 'metadata';

      const playBtn = document.createElement('button');
      playBtn.className = 'audio-player__play-btn';
      playBtn.type = 'button';
      playBtn.setAttribute('aria-label', '再生');
      playBtn.innerHTML = '&#9654;';

      const seek = document.createElement('input');
      seek.className = 'audio-player__seek';
      seek.type = 'range';
      seek.min = '0';
      seek.max = '1';
      seek.step = '0.001';
      seek.value = '0';

      const timeDisplay = document.createElement('span');
      timeDisplay.className = 'audio-player__time';
      timeDisplay.textContent = '00:00 / 00:00';

      const muteBtn = document.createElement('button');
      muteBtn.className = 'audio-player__mute-btn';
      muteBtn.type = 'button';
      muteBtn.setAttribute('aria-label', 'ミュート');
      muteBtn.innerHTML = '&#128266;';

      const volumeSlider = document.createElement('input');
      volumeSlider.className = 'audio-player__volume';
      volumeSlider.type = 'range';
      volumeSlider.min = '0';
      volumeSlider.max = '1';
      volumeSlider.step = '0.01';
      volumeSlider.value = '1';

      root.append(audio, playBtn, seek, timeDisplay, muteBtn, volumeSlider);

      this.audio = audio;
      this.playBtn = playBtn;
      this.seekSlider = seek;
      this.timeDisplay = timeDisplay;
      this.muteBtn = muteBtn;
      this.volumeSlider = volumeSlider;
    }

    /* ── イベント登録 ── */
    _bind() {
      const self = this;

      this._onPlayClick = function () { self.toggle(); };
      this._onMuteClick = function () { self.toggleMute(); };

      this._onSeekPointerDown = function () { self._seeking = true; };
      this._onSeekPointerUp = function () {
        if (Number.isFinite(self.audio.duration) && self.audio.duration > 0) {
          self.audio.currentTime = parseFloat(self.seekSlider.value) * self.audio.duration;
        }
        self._seeking = false;
      };
      this._onSeekInput = function () {
        /* ポインターが押されている間だけ時間表示を先行更新 */
        if (Number.isFinite(self.audio.duration) && self.audio.duration > 0) {
          const t = parseFloat(self.seekSlider.value) * self.audio.duration;
          self.timeDisplay.textContent = formatTime(t) + ' / ' + formatTime(self.audio.duration);
        }
      };

      this._onVolumeInput = function () {
        self.control.setVolume(parseFloat(self.volumeSlider.value));
      };

      this._onAudioPlay = function () {
        self.control.notifyPlay(self);
        self._updateButton();
      };
      this._onAudioPause = function () { self._updateButton(); };
      this._onAudioEnded = function () { self._updateButton(); };
      this._onLoadedMetadata = function () { self._updateTime(); };
      this._onTimeUpdate = function () { self._updateTime(); };

      this.playBtn.addEventListener('click', this._onPlayClick);
      this.muteBtn.addEventListener('click', this._onMuteClick);
      this.seekSlider.addEventListener('pointerdown', this._onSeekPointerDown);
      this.seekSlider.addEventListener('pointerup', this._onSeekPointerUp);
      this.seekSlider.addEventListener('input', this._onSeekInput);
      this.volumeSlider.addEventListener('input', this._onVolumeInput);
      this.audio.addEventListener('play', this._onAudioPlay);
      this.audio.addEventListener('pause', this._onAudioPause);
      this.audio.addEventListener('ended', this._onAudioEnded);
      this.audio.addEventListener('loadedmetadata', this._onLoadedMetadata);
      this.audio.addEventListener('timeupdate', this._onTimeUpdate);
    }

    /* ── 内部ヘルパー ── */

    _updateButton() {
      const paused = this.audio.paused || this.audio.ended;
      this.playBtn.innerHTML = paused ? '&#9654;' : '&#9646;&#9646;';
      this.playBtn.setAttribute('aria-label', paused ? '再生' : '一時停止');
    }

    _updateTime() {
      if (this._seeking) return;
      const cur = this.audio.currentTime;
      const dur = this.audio.duration;
      if (Number.isFinite(dur) && dur > 0) {
        this.seekSlider.value = String(clamp(cur / dur, 0, 1));
      }
      this.timeDisplay.textContent = formatTime(cur) + ' / ' + formatTime(dur);
    }

    /** コントロールの音量をこのプレイヤーに適用（volumeSlider も更新）。 */
    _applyVolume(value) {
      value = clamp(value, 0, 1);
      this.audio.volume = value;
      this.volumeSlider.value = String(value);
    }

    /* ── 公開 API ── */

    /**
     * 音声ファイルを切り替える。
     * @param {string} url
     * @param {boolean} [autoplay]
     */
    load(url, autoplay) {
      if (this.destroyed) return;
      this.audio.pause();
      this.audio.src = url;
      this.audio.load();
      this.seekSlider.value = '0';
      this.timeDisplay.textContent = '00:00 / 00:00';
      this._updateButton();
      if (autoplay == null ? this.autoplay : autoplay) {
        const self = this;
        this.audio.addEventListener('canplay', function handler() {
          self.audio.removeEventListener('canplay', handler);
          const p = self.play();
          if (p && p.catch) p.catch(function () {});
        });
      }
    }

    play() {
      if (this.destroyed) return;
      return this.audio.play();
    }

    pause() {
      if (this.destroyed) return;
      this.audio.pause();
    }

    toggle() {
      if (this.audio.paused || this.audio.ended) {
        const p = this.play();
        if (p && p.catch) p.catch(function () {});
      } else {
        this.pause();
      }
    }

    toggleMute() {
      this.audio.muted = !this.audio.muted;
      this.muteBtn.innerHTML = this.audio.muted ? '&#128263;' : '&#128266;';
      this.muteBtn.setAttribute('aria-label', this.audio.muted ? 'ミュート解除' : 'ミュート');
    }

    destroy() {
      if (this.destroyed) return;
      this.destroyed = true;

      this.audio.pause();
      this.audio.src = '';

      this.playBtn.removeEventListener('click', this._onPlayClick);
      this.muteBtn.removeEventListener('click', this._onMuteClick);
      this.seekSlider.removeEventListener('pointerdown', this._onSeekPointerDown);
      this.seekSlider.removeEventListener('pointerup', this._onSeekPointerUp);
      this.seekSlider.removeEventListener('input', this._onSeekInput);
      this.volumeSlider.removeEventListener('input', this._onVolumeInput);
      this.audio.removeEventListener('play', this._onAudioPlay);
      this.audio.removeEventListener('pause', this._onAudioPause);
      this.audio.removeEventListener('ended', this._onAudioEnded);
      this.audio.removeEventListener('loadedmetadata', this._onLoadedMetadata);
      this.audio.removeEventListener('timeupdate', this._onTimeUpdate);

      this.control.unregister(this);
      AudioPlayer._players.delete(this.name);

      if (this.root) this.root.innerHTML = '';
    }
  }

  AudioPlayer._players = new Map();

  /* ── グローバル公開 ── */
  root.AudioPlayer = AudioPlayer;
  root.AudioPlayerControl = AudioPlayerControl;

})(window);
