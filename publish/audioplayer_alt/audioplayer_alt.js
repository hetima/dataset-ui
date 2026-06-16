typeof navigator === "object" && (function (global, factory) {
  typeof exports === 'object' && typeof module !== 'undefined' ? module.exports = factory() :
  typeof define === 'function' && define.amd ? define('PlyrAlt', factory) :
  (global = typeof globalThis !== 'undefined' ? globalThis : global || self, global.PlyrAlt = factory());
})(this, (function () { 'use strict';

  function _defineProperty(e, r, t) {
    return (r = _toPropertyKey(r)) in e ? Object.defineProperty(e, r, {
      value: t,
      enumerable: true,
      configurable: true,
      writable: true
    }) : e[r] = t, e;
  }
  function _toPrimitive(t, r) {
    if ("object" != typeof t || !t) return t;
    var e = t[Symbol.toPrimitive];
    if (void 0 !== e) {
      var i = e.call(t, r);
      if ("object" != typeof i) return i;
      throw new TypeError("@@toPrimitive must return a primitive value.");
    }
    return ("string" === r ? String : Number)(t);
  }
  function _toPropertyKey(t) {
    var i = _toPrimitive(t, "string");
    return "symbol" == typeof i ? i : i + "";
  }

  // ==========================================================================
  // PlyrAlt
  // NiceGUI から埋め込みやすい、波形表示付きの軽量 audio プレイヤーです。
  // ==========================================================================

  const defaultOptions = {
    src: null,
    label: '',
    control: null,
    height: 96,
    barWidth: 2,
    barGap: 1,
    peakCount: 2048,
    colors: {
      background: '#f6f8fb',
      wave: '#b8c1cc',
      progress: '#00b2ff',
      text: '#26323f',
      control: '#26323f',
      controlBackground: 'rgba(255, 255, 255, 0.86)'
    }
  };
  const clamp = (value, min, max) => Math.min(Math.max(value, min), max);
  const isElement = value => value instanceof Element;
  const normalizeVolume = (value, fallback = 1) => {
    const volume = Number(value);
    return Number.isFinite(volume) ? clamp(volume, 0, 1) : fallback;
  };
  const formatTime = seconds => {
    if (!Number.isFinite(seconds) || seconds < 0) {
      return '00:00';
    }
    const totalSeconds = Math.floor(seconds);
    const minutes = Math.floor(totalSeconds / 60);
    const remainingSeconds = totalSeconds % 60;
    return `${String(minutes).padStart(2, '0')}:${String(remainingSeconds).padStart(2, '0')}`;
  };
  const resolveElement = target => {
    if (isElement(target)) {
      return target;
    }
    if (typeof target === 'string') {
      return document.querySelector(target);
    }
    return null;
  };
  const mergeOptions = options => ({
    ...defaultOptions,
    ...options,
    colors: {
      ...defaultOptions.colors,
      ...(options && options.colors ? options.colors : {})
    }
  });
  class PlyrAltControl {
    /** 指定 ID の共有コントローラーを取得します。なければ作成します。 */
    static get(id = 'default', options = {}) {
      if (!PlyrAltControl.controls.has(id)) {
        PlyrAltControl.controls.set(id, new PlyrAltControl({
          ...options,
          id
        }));
      }
      return PlyrAltControl.controls.get(id);
    }
    constructor(options = {}) {
      this.id = options.id || `plyr-alt-control-${Math.random().toString(36).slice(2)}`;
      this.players = new Set();
      this.current = null;
      this.volume = normalizeVolume(options.volume);
      this.element = null;
      this.input = null;
      PlyrAltControl.controls.set(this.id, this);
    }

    /** プレイヤーを共有管理の対象に追加します。 */
    register(player) {
      this.players.add(player);
      player.setVolume(this.volume);
    }

    /** プレイヤーを共有管理から外します。 */
    unregister(player) {
      this.players.delete(player);
      if (this.current === player) {
        this.current = null;
      }
    }

    /** ひとつの再生開始に合わせて他のプレイヤーを停止します。 */
    notifyPlay(activePlayer) {
      this.current = activePlayer;
      this.players.forEach(player => {
        if (player !== activePlayer) {
          player.pause();
        }
      });
    }

    /** 共有ボリュームを全プレイヤーへ反映します。 */
    setVolume(value) {
      this.volume = normalizeVolume(value, this.volume);
      if (this.input) {
        this.input.value = String(this.volume);
      }
      this.players.forEach(player => player.setVolume(this.volume));
    }

    /** NiceGUI などから渡された要素へ共有ボリューム UI を描画します。 */
    mount(target) {
      const element = resolveElement(target);
      if (!element) {
        throw new Error('PlyrAltControl mount target was not found.');
      }
      this.element = element;
      element.classList.add('plyr-alt-control');
      element.innerHTML = '';
      const label = document.createElement('label');
      label.className = 'plyr-alt-control__label';
      label.textContent = 'Volume';
      const input = document.createElement('input');
      input.className = 'plyr-alt-control__range';
      input.type = 'range';
      input.min = '0';
      input.max = '1';
      input.step = '0.01';
      input.value = String(this.volume);
      input.addEventListener('input', () => this.setVolume(input.value));
      label.appendChild(input);
      element.appendChild(label);
      this.input = input;
    }
  }
  _defineProperty(PlyrAltControl, "controls", new Map());
  class PlyrAlt {
    /** 指定 ID のプレイヤーを取得します。 */
    static get(id) {
      return PlyrAlt.players.get(id) || null;
    }

    /** 指定 ID のプレイヤーを破棄します。 */
    static destroy(id, options = {}) {
      const player = PlyrAlt.get(id);
      if (!player) {
        return;
      }
      player.destroy(options);
    }
    constructor(target, options = {}) {
      this.options = mergeOptions(options);
      this.root = resolveElement(target);
      if (!this.root) {
        throw new Error('PlyrAlt target was not found.');
      }
      this.audio = null;
      this.canvas = null;
      this.context = null;
      this.button = null;
      this.label = null;
      this.time = null;
      this.peaks = [];
      this.waveformReady = false;
      this.waveformFailed = false;
      this.animationFrame = null;
      this.destroyed = false;
      this.id = this.options.id || this.root.id || `plyr-alt-${Math.random().toString(36).slice(2)}`;
      this.control = this.resolveControl(this.options.control);
      this.build();
      this.bind();
      this.control.register(this);
      PlyrAlt.players.set(this.id, this);
      this.loadWaveform();
    }

    /** control オプションを共有コントローラーへ解決します。 */
    resolveControl(control) {
      if (control instanceof PlyrAltControl) {
        return control;
      }
      if (typeof control === 'string') {
        return PlyrAltControl.get(control);
      }
      return PlyrAltControl.get('default');
    }

    /** audio と canvas を含む表示 UI を構築します。 */
    build() {
      let audio = this.root.matches('audio') ? this.root : this.root.querySelector('audio');
      const container = this.root.matches('audio') ? document.createElement('div') : this.root;
      if (this.root.matches('audio')) {
        this.root.parentNode.insertBefore(container, this.root);
        container.appendChild(this.root);
      }
      if (!audio) {
        audio = document.createElement('audio');
        container.appendChild(audio);
      }
      if (this.options.src) {
        audio.src = this.options.src;
      }
      audio.preload = audio.preload || 'metadata';
      audio.controls = false;
      audio.classList.add('plyr-alt__audio');
      container.classList.add('plyr-alt');
      container.style.setProperty('--plyr-alt-height', `${this.options.height}px`);
      container.style.setProperty('--plyr-alt-background', this.options.colors.background);
      container.style.setProperty('--plyr-alt-text', this.options.colors.text);
      container.style.setProperty('--plyr-alt-control', this.options.colors.control);
      container.style.setProperty('--plyr-alt-control-background', this.options.colors.controlBackground);
      const canvas = document.createElement('canvas');
      canvas.className = 'plyr-alt__waveform';
      const label = document.createElement('div');
      label.className = 'plyr-alt__label';
      label.textContent = this.options.label || audio.getAttribute('data-label') || audio.currentSrc || audio.src || '';
      const button = document.createElement('button');
      button.className = 'plyr-alt__play';
      button.type = 'button';
      button.setAttribute('aria-label', 'Play');
      button.textContent = 'Play';
      const time = document.createElement('div');
      time.className = 'plyr-alt__time';
      time.textContent = '00:00 / 00:00';
      container.appendChild(canvas);
      container.appendChild(label);
      container.appendChild(button);
      container.appendChild(time);
      this.root = container;
      this.root.id = this.id;
      this.root.dataset.plyrAltId = this.id;
      this.audio = audio;
      this.canvas = canvas;
      this.context = canvas.getContext('2d');
      this.label = label;
      this.button = button;
      this.time = time;
      this.resizeObserver = new ResizeObserver(() => this.draw());
      this.resizeObserver.observe(this.root);
    }

    /** audio と UI のイベントを接続します。 */
    bind() {
      this.onPlayClick = () => this.toggle();
      this.onCanvasClick = event => this.seekFromEvent(event);
      this.onPlay = () => {
        this.control.notifyPlay(this);
        this.updateButton();
        this.updateTime();
        this.startDrawing();
      };
      this.onPause = () => {
        this.updateButton();
        this.updateTime();
        this.stopDrawing();
        this.draw();
      };
      this.onEnded = () => {
        this.updateButton();
        this.updateTime();
        this.stopDrawing();
        this.draw();
      };
      this.onLoadedMetadata = () => {
        this.updateTime();
        this.draw();
      };
      this.onTimeUpdate = () => this.updateTime();
      this.onDurationChange = () => this.updateTime();
      this.button.addEventListener('click', this.onPlayClick);
      this.canvas.addEventListener('click', this.onCanvasClick);
      this.audio.addEventListener('play', this.onPlay);
      this.audio.addEventListener('pause', this.onPause);
      this.audio.addEventListener('ended', this.onEnded);
      this.audio.addEventListener('loadedmetadata', this.onLoadedMetadata);
      this.audio.addEventListener('timeupdate', this.onTimeUpdate);
      this.audio.addEventListener('durationchange', this.onDurationChange);
    }

    /** ブラウザ側で音声を decode して波形 peaks を生成します。 */
    async loadWaveform() {
      const src = this.audio.currentSrc || this.audio.src;
      if (!src) {
        this.waveformFailed = true;
        this.draw();
        return;
      }
      try {
        const response = await fetch(src);
        if (!response.ok) {
          throw new Error(`Waveform request failed: ${response.status}`);
        }
        const arrayBuffer = await response.arrayBuffer();
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (!AudioContextClass) {
          throw new Error('Web Audio API is not available.');
        }
        const audioContext = new AudioContextClass();
        const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
        this.peaks = this.createPeaks(audioBuffer);
        this.waveformReady = true;
        if (audioContext.close) {
          audioContext.close();
        }
      } catch {
        this.waveformFailed = true;
      }
      if (this.destroyed) {
        return;
      }
      this.draw();
    }

    /** 表示幅に依存しない固定本数で全チャンネル最大振幅の peaks を作ります。 */
    createPeaks(audioBuffer) {
      const bars = Math.max(1, Math.round(this.options.peakCount));
      const blockSize = Math.max(1, Math.floor(audioBuffer.length / bars));
      const peaks = [];
      for (let index = 0; index < bars; index += 1) {
        let peak = 0;
        const start = index * blockSize;
        const end = Math.min(start + blockSize, audioBuffer.length);
        for (let channel = 0; channel < audioBuffer.numberOfChannels; channel += 1) {
          const data = audioBuffer.getChannelData(channel);
          let channelPeak = 0;
          for (let sample = start; sample < end; sample += 1) {
            channelPeak = Math.max(channelPeak, Math.abs(data[sample]));
          }
          peak += channelPeak;
        }
        peaks.push(clamp(peak / audioBuffer.numberOfChannels, 0, 1));
      }
      return peaks;
    }

    /** canvas のサイズと再生位置に合わせて波形を描画します。 */
    draw() {
      if (!this.context) {
        return;
      }
      const width = Math.max(1, Math.round(this.root.clientWidth));
      const height = Math.max(1, Math.round(this.root.clientHeight || this.options.height));
      const ratio = window.devicePixelRatio || 1;
      if (this.canvas.width !== width * ratio || this.canvas.height !== height * ratio) {
        this.canvas.width = width * ratio;
        this.canvas.height = height * ratio;
        this.canvas.style.width = `${width}px`;
        this.canvas.style.height = `${height}px`;
        this.context.setTransform(ratio, 0, 0, ratio, 0, 0);
      }
      this.context.clearRect(0, 0, width, height);
      this.context.fillStyle = this.options.colors.background;
      this.context.fillRect(0, 0, width, height);
      const progress = Number.isFinite(this.audio.duration) && this.audio.duration > 0 ? clamp(this.audio.currentTime / this.audio.duration, 0, 1) : 0;
      this.drawBars(width, height, this.options.colors.wave);
      this.context.save();
      this.context.beginPath();
      this.context.rect(0, 0, width * progress, height);
      this.context.clip();
      this.drawBars(width, height, this.options.colors.progress);
      this.context.restore();
    }

    /** 現在時刻と総時間の表示を更新します。 */
    updateTime() {
      if (!this.time) {
        return;
      }
      this.time.textContent = `${formatTime(this.audio.currentTime)} / ${formatTime(this.audio.duration)}`;
    }

    /** peaks がない場合は中央線、ある場合は棒状の波形を描きます。 */
    drawBars(width, height, color) {
      const center = height / 2;
      const controlsOffset = 34;
      const topPadding = 30;
      const bottomPadding = 14;
      const usableHeight = Math.max(8, height - topPadding - bottomPadding);
      const barWidth = this.options.barWidth;
      const step = barWidth + this.options.barGap;
      const rightPadding = 10;
      const drawableWidth = Math.max(0, width - controlsOffset - rightPadding);
      const barCount = Math.max(1, Math.floor(drawableWidth / step));
      this.context.fillStyle = color;
      if (!this.waveformReady || this.peaks.length === 0) {
        this.context.fillRect(controlsOffset, center - 1, drawableWidth, 2);
        return;
      }
      for (let index = 0; index < barCount; index += 1) {
        const peakIndex = Math.min(this.peaks.length - 1, Math.floor(index / barCount * this.peaks.length));
        const peak = this.peaks[peakIndex];
        const x = controlsOffset + index * step;
        const barHeight = Math.max(2, peak * usableHeight);
        this.context.fillRect(x, center - barHeight / 2, barWidth, barHeight);
      }
    }

    /** canvas クリック位置から再生位置を変更します。 */
    seekFromEvent(event) {
      if (!Number.isFinite(this.audio.duration) || this.audio.duration <= 0) {
        return;
      }
      const wasPaused = this.audio.paused;
      const rect = this.canvas.getBoundingClientRect();
      const ratio = clamp((event.clientX - rect.left) / rect.width, 0, 1);
      this.audio.currentTime = ratio * this.audio.duration;
      this.draw();
      if (wasPaused) {
        const playback = this.play();
        if (playback && typeof playback.catch === 'function') {
          playback.catch(() => {});
        }
      }
    }

    /** 再生と停止を切り替えます。 */
    toggle() {
      if (this.audio.paused) {
        this.play();
      } else {
        this.pause();
      }
    }

    /** 再生を開始します。 */
    play() {
      return this.audio.play();
    }

    /** 再生を停止します。 */
    pause() {
      this.audio.pause();
    }

    /** 共有ボリュームを audio 要素へ反映します。 */
    setVolume(value) {
      this.audio.volume = normalizeVolume(value, this.audio.volume);
    }

    /** 再生状態に合わせてボタン表示を更新します。 */
    updateButton() {
      const playing = !this.audio.paused;
      this.button.textContent = playing ? 'Pause' : 'Play';
      this.button.setAttribute('aria-label', playing ? 'Pause' : 'Play');
      this.root.classList.toggle('plyr-alt--playing', playing);
    }

    /** 再生中の波形更新ループを開始します。 */
    startDrawing() {
      this.stopDrawing();
      const tick = () => {
        this.draw();
        if (!this.audio.paused && !this.audio.ended) {
          this.animationFrame = window.requestAnimationFrame(tick);
        }
      };
      this.animationFrame = window.requestAnimationFrame(tick);
    }

    /** 波形更新ループを停止します。 */
    stopDrawing() {
      if (this.animationFrame) {
        window.cancelAnimationFrame(this.animationFrame);
        this.animationFrame = null;
      }
    }

    /** イベントと共有管理を解除します。 */
    destroy(options = {}) {
      if (this.destroyed) {
        return;
      }
      this.destroyed = true;
      this.stopDrawing();
      this.control.unregister(this);
      PlyrAlt.players.delete(this.id);
      this.button.removeEventListener('click', this.onPlayClick);
      this.canvas.removeEventListener('click', this.onCanvasClick);
      this.audio.removeEventListener('play', this.onPlay);
      this.audio.removeEventListener('pause', this.onPause);
      this.audio.removeEventListener('ended', this.onEnded);
      this.audio.removeEventListener('loadedmetadata', this.onLoadedMetadata);
      this.audio.removeEventListener('timeupdate', this.onTimeUpdate);
      this.audio.removeEventListener('durationchange', this.onDurationChange);
      if (this.resizeObserver) {
        this.resizeObserver.disconnect();
      }
      if (options.removeElement && this.root.parentNode) {
        this.root.parentNode.removeChild(this.root);
      }
    }
  }
  _defineProperty(PlyrAlt, "players", new Map());
  PlyrAlt.PlyrAltControl = PlyrAltControl;
  if (typeof window !== 'undefined') {
    window.PlyrAlt = PlyrAlt;
    window.PlyrAltControl = PlyrAltControl;
  }

  return PlyrAlt;

}));
//# sourceMappingURL=plyr-alt.js.map
