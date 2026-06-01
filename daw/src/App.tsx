import {
  createContext,
  type Dispatch,
  type SetStateAction,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import {
  AlertTriangle,
  LoaderCircle,
  Pause,
  Play,
  Redo2,
  RefreshCw,
  Scissors,
  Server,
  Square,
  Undo2,
  Volume2,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'
import {
  ClipInteractionProvider,
  type ClipTrack,
  KeyboardShortcuts,
  Waveform,
  WaveformPlaylistProvider,
  useAudioTracks,
  useClipSplitting,
  usePlaybackAnimation,
  usePlaylistControls,
  usePlaylistData,
  usePlaylistState,
} from '@waveform-playlist/browser'
import './App.css'

type DawTrack = {
  id: string
  name: string
  sourcePath: string
  url: string
  volume: number
  muted: boolean
  soloed: boolean
  startTime: number
}

type DawSession = {
  id: string
  tracks: DawTrack[]
}

type SoloPlaybackState = {
  trackIndex: number
  startTime: number
  soloedStates: boolean[]
}

type SoloPlaybackContextValue = {
  soloPlayback: SoloPlaybackState | null
  setSoloPlayback: Dispatch<SetStateAction<SoloPlaybackState | null>>
}

type IoRangeState = {
  inPoint: number | null
  outPoint: number | null
  loop: boolean
}

type IoRangeContextValue = {
  ioRange: IoRangeState
  setIoRange: Dispatch<SetStateAction<IoRangeState>>
  scrollLeft: number
}

const SoloPlaybackContext = createContext<SoloPlaybackContextValue | null>(null)
const IoRangeContext = createContext<IoRangeContextValue | null>(null)

function useSoloPlayback() {
  const context = useContext(SoloPlaybackContext)
  if (!context) {
    throw new Error('SoloPlaybackContext が見つかりません')
  }
  return context
}

function useIoRange() {
  const context = useContext(IoRangeContext)
  if (!context) {
    throw new Error('IoRangeContext が見つかりません')
  }
  return context
}

async function fetchSession(id: string) {
  const response = await fetch(`/api/daw/session/${id}`)
  if (!response.ok) {
    throw new Error(`セッション取得に失敗しました (${response.status})`)
  }
  return (await response.json()) as DawSession
}

function App() {
  const params = useMemo(() => new URLSearchParams(window.location.search), [])
  const sessionId = params.get('session') ?? ''
  const [session, setSession] = useState<DawSession | null>(null)
  const [loading, setLoading] = useState(Boolean(sessionId))
  const [error, setError] = useState('')

  const reloadSession = async () => {
    if (!sessionId) {
      setError('session が指定されていません')
      return
    }

    setLoading(true)
    setError('')
    try {
      setSession(await fetchSession(sessionId))
    } catch (err) {
      setSession(null)
      setError(err instanceof Error ? err.message : 'セッション取得に失敗しました')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let ignore = false
    if (!sessionId) {
      return
    }

    fetchSession(sessionId)
      .then((data) => {
        if (!ignore) {
          setSession(data)
        }
      })
      .catch((err) => {
        if (!ignore) {
          setError(err instanceof Error ? err.message : 'セッション取得に失敗しました')
        }
      })
      .finally(() => {
        if (!ignore) {
          setLoading(false)
        }
      })

    return () => {
      ignore = true
    }
  }, [sessionId])

  const displayError = !sessionId ? 'session が指定されていません' : error

  return (
    <main className="daw-shell">
      <header className="topbar">
        <div>
          <h1>DAW</h1>
          <p>NiceGUI から渡された音声ファイルを確認します</p>
        </div>
        <button type="button" className="toolbar-button" onClick={reloadSession}>
          <RefreshCw size={17} />
          再読み込み
        </button>
      </header>

      <section className="status-line">
        <span>
          <Server size={16} />
          session: {sessionId || '-'}
        </span>
        {loading && (
          <span>
            <LoaderCircle size={16} className="spin" />
            読み込み中
          </span>
        )}
      </section>

      {displayError && (
        <section className="notice error">
          <AlertTriangle size={18} />
          {displayError}
        </section>
      )}

      {session && (
        <section className="track-panel">
          <div className="panel-header">
            <h2>Tracks</h2>
            <span>{session.tracks.length} files</span>
          </div>

          <PlaylistArea sourceTracks={session.tracks} />
        </section>
      )}
    </main>
  )
}

function PlaylistArea({ sourceTracks }: { sourceTracks: DawTrack[] }) {
  const configs = useMemo(
    () =>
      sourceTracks.map((track) => ({
        src: track.url,
        name: track.name,
        volume: track.volume,
        muted: track.muted,
        soloed: track.soloed,
        startTime: track.startTime,
      })),
    [sourceTracks],
  )
  const { tracks, loading, error, loadedCount, totalCount } = useAudioTracks(configs)

  return (
    <div className="playlist-shell">
      {error && (
        <div className="notice error">
          <AlertTriangle size={18} />
          {error}
        </div>
      )}
      {loading && (
        <div className="playlist-loading">
          <LoaderCircle size={18} className="spin" />
          読み込み {loadedCount}/{totalCount}
        </div>
      )}
      {!loading && tracks.length > 0 && (
        <EditablePlaylist key={sourceTracks.map((track) => track.id).join(':')} initialTracks={tracks} />
      )}
    </div>
  )
}

function EditablePlaylist({ initialTracks }: { initialTracks: ClipTrack[] }) {
  const [playlistTracks, setPlaylistTracks] = useState(initialTracks)
  const [soloPlayback, setSoloPlayback] = useState<SoloPlaybackState | null>(null)
  const [ioRange, setIoRange] = useState<IoRangeState>({
    inPoint: null,
    outPoint: null,
    loop: false,
  })
  const [scrollLeft, setScrollLeft] = useState(0)
  const viewportRef = useRef<HTMLDivElement | null>(null)

  return (
    <WaveformPlaylistProvider
      tracks={playlistTracks}
      onTracksChange={setPlaylistTracks}
      timescale
      waveHeight={76}
      samplesPerPixel={2048}
      controls={{ show: true, width: 240 }}
    >
      <KeyboardShortcuts playback clipSplitting undo />
      <PlaylistToolbar />
      <SoloPlaybackContext.Provider value={{ soloPlayback, setSoloPlayback }}>
        <IoRangeContext.Provider value={{ ioRange, setIoRange, scrollLeft }}>
          <IoKeyboardShortcuts />
          <ClipInteractionProvider>
            <div
              ref={viewportRef}
              className="playlist-view"
              onScroll={(event) => setScrollLeft(event.currentTarget.scrollLeft)}
            >
              <IoHeaderControls />
              <IoRulerMarkers />
              <RulerClickOverlay viewportRef={viewportRef} />
              <Waveform
                showClipHeaders
                showFades
                renderTrackControls={(trackIndex) => <TrackControls trackIndex={trackIndex} />}
              />
            </div>
          </ClipInteractionProvider>
        </IoRangeContext.Provider>
      </SoloPlaybackContext.Provider>
    </WaveformPlaylistProvider>
  )
}

function getIoRangeBounds(ioRange: IoRangeState) {
  if (ioRange.inPoint === null || ioRange.outPoint === null) {
    return null
  }

  const start = Math.min(ioRange.inPoint, ioRange.outPoint)
  const end = Math.max(ioRange.inPoint, ioRange.outPoint)
  if (end <= start) {
    return null
  }
  return { start, end, duration: end - start }
}

function shouldIgnoreIoShortcut(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) {
    return false
  }

  return Boolean(
    target.closest('input, textarea, select, button, [contenteditable="true"]'),
  )
}

function IoKeyboardShortcuts() {
  const playback = usePlaybackAnimation()
  const { setIoRange } = useIoRange()

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.repeat || shouldIgnoreIoShortcut(event.target)) {
        return
      }

      const key = event.key.toLowerCase()
      if (key !== 'i' && key !== 'o') {
        return
      }

      event.preventDefault()
      const time = Math.max(0, playback.currentTimeRef.current ?? 0)
      setIoRange((current) =>
        key === 'i' ? { ...current, inPoint: time } : { ...current, outPoint: time },
      )
    }

    window.addEventListener('keydown', onKeyDown)
    try {
      if (window.parent !== window) {
        window.parent.addEventListener('keydown', onKeyDown)
      }
    } catch {
      // クロスオリジン埋め込み時は iframe 内だけで受ける
    }

    return () => {
      window.removeEventListener('keydown', onKeyDown)
      try {
        if (window.parent !== window) {
          window.parent.removeEventListener('keydown', onKeyDown)
        }
      } catch {
        // クロスオリジン埋め込み時は解除不要
      }
    }
  }, [playback.currentTimeRef, setIoRange])

  return null
}

function IoHeaderControls() {
  const controls = usePlaylistControls()
  const playback = usePlaybackAnimation()
  const { ioRange, setIoRange } = useIoRange()
  const range = useMemo(
    () => getIoRangeBounds(ioRange),
    [ioRange],
  )
  const ioPlaybackActiveRef = useRef(false)
  const loopResumePendingRef = useRef(false)

  useEffect(() => {
    if (!ioPlaybackActiveRef.current || loopResumePendingRef.current || !range) {
      return
    }
    if (playback.isPlaying) {
      return
    }

    const currentTime = playback.currentTimeRef.current ?? 0
    const reachedOutPoint = currentTime >= range.end - 0.05
    if (!reachedOutPoint) {
      ioPlaybackActiveRef.current = false
      return
    }

    if (!ioRange.loop) {
      ioPlaybackActiveRef.current = false
      return
    }

    loopResumePendingRef.current = true
    controls.setCurrentTime(range.start)
    void controls.play(range.start, range.duration).finally(() => {
      loopResumePendingRef.current = false
    })
  }, [controls, ioRange.loop, playback.currentTimeRef, playback.isPlaying, range])

  const playIoRange = async () => {
    if (!range) {
      return
    }

    ioPlaybackActiveRef.current = true
    loopResumePendingRef.current = false
    controls.stop()
    controls.setCurrentTime(range.start)
    await controls.play(range.start, range.duration)
  }

  const toggleLoop = (checked: boolean) => {
    setIoRange((current) => ({ ...current, loop: checked }))
  }

  return (
    <div className="io-header-controls">
      <button
        type="button"
        className="io-play-button"
        disabled={!range}
        onMouseDown={(event) => event.stopPropagation()}
        onClick={() => void playIoRange()}
      >
        <Play size={12} />
        IO再生
      </button>
      <label className="io-loop-control" onMouseDown={(event) => event.stopPropagation()}>
        <input
          type="checkbox"
          checked={ioRange.loop}
          onChange={(event) => toggleLoop(event.currentTarget.checked)}
        />
        IOループ
      </label>
    </div>
  )
}

function IoRulerMarkers() {
  const data = usePlaylistData()
  const { ioRange, scrollLeft } = useIoRange()
  const controlsWidth = data.controls.show ? data.controls.width : 0
  const range = useMemo(
    () => getIoRangeBounds(ioRange),
    [ioRange],
  )

  const timeToPixel = (time: number) =>
    controlsWidth + time * data.sampleRate / data.samplesPerPixel - scrollLeft

  const inLeft = ioRange.inPoint === null ? null : timeToPixel(ioRange.inPoint)
  const outLeft = ioRange.outPoint === null ? null : timeToPixel(ioRange.outPoint)
  const rangeLeft = range ? timeToPixel(range.start) : 0
  const rangeRight = range ? timeToPixel(range.end) : 0

  return (
    <div className="io-ruler-layer" style={{ left: controlsWidth }}>
      {range && (
        <div
          className="io-range-region"
          style={{
            left: rangeLeft - controlsWidth,
            width: Math.max(1, rangeRight - rangeLeft),
          }}
        />
      )}
      {inLeft !== null && (
        <div className="io-marker io-marker-in" style={{ left: inLeft - controlsWidth }}>
          I
        </div>
      )}
      {outLeft !== null && (
        <div className="io-marker io-marker-out" style={{ left: outLeft - controlsWidth }}>
          O
        </div>
      )}
    </div>
  )
}

function RulerClickOverlay({
  viewportRef,
}: {
  viewportRef: React.RefObject<HTMLDivElement | null>
}) {
  const controls = usePlaylistControls()
  const data = usePlaylistData()
  const dragStateRef = useRef<{
    dragging: boolean
    startY: number
    lastStep: number
    rulerLeft: number
    zooming: boolean
  } | null>(null)
  const zoomAnchorRef = useRef<{
    time: number
    x: number
  } | null>(null)

  const controlsWidth = data.controls.show ? data.controls.width : 0

  const pixelToTime = (clientX: number, rulerLeft: number, viewport: HTMLDivElement) => {
    const waveformPixel = clientX - rulerLeft + viewport.scrollLeft
    const clampedPixel = Math.max(0, waveformPixel)
    const seconds = (clampedPixel * data.samplesPerPixel) / data.sampleRate
    return Math.max(0, Math.min(seconds, data.duration || seconds))
  }

  useEffect(() => {
    const viewport = viewportRef.current
    const anchor = zoomAnchorRef.current
    if (!viewport || !anchor) {
      return
    }

    // ズーム変化後、アンカー時刻が画面上の同じピクセル位置に来るようスクロールを補正
    // anchor.x はスクロールを含むwaveformピクセル座標
    const nextScrollLeft = anchor.time * data.sampleRate / data.samplesPerPixel - anchor.x
    viewport.scrollLeft = Math.max(0, nextScrollLeft)
  }, [data.sampleRate, data.samplesPerPixel, viewportRef])

  const applyZoomStep = (stepDelta: number) => {
    if (stepDelta > 0) {
      for (let i = 0; i < stepDelta; i += 1) {
        controls.zoomIn()
      }
      return
    }
    for (let i = 0; i < Math.abs(stepDelta); i += 1) {
      controls.zoomOut()
    }
  }

  const updateZoomFromPointer = (state: { startY: number; lastStep: number }, clientY: number) => {
    const deltaY = clientY - state.startY
    const step = Math.trunc(deltaY / 24)
    if (step === state.lastStep) {
      return
    }

    applyZoomStep(step - state.lastStep)
    state.lastStep = step
  }

  const updateSeekFromPointer = (clientX: number, rulerLeft: number) => {
    const viewport = viewportRef.current
    if (!viewport) {
      return
    }

    const time = pixelToTime(clientX, rulerLeft, viewport)
    // x はスクロールを含むwaveformピクセル座標（ズームアンカー補正に使う）
    const x = Math.max(0, clientX - rulerLeft + viewport.scrollLeft)
    zoomAnchorRef.current = { time, x }
    controls.setCurrentTime(time)
    controls.setSelection(time, time)
  }

  const stopWindowDrag = () => {
    window.removeEventListener('mousemove', onWindowMouseMove)
    window.removeEventListener('mouseup', onWindowMouseUp)
    dragStateRef.current = null
  }

  const onWindowMouseMove = (event: MouseEvent) => {
    const state = dragStateRef.current
    if (!state?.dragging) {
      return
    }

    event.preventDefault()
    // 縦方向に8px以上動いたらズームモード（シーク更新を止める）
    const absY = Math.abs(event.clientY - state.startY)
    if (absY >= 8) {
      state.zooming = true
    }
    if (state.zooming) {
      updateZoomFromPointer(state, event.clientY)
    } else {
      updateSeekFromPointer(event.clientX, state.rulerLeft)
    }
  }

  const onWindowMouseUp = (event: MouseEvent) => {
    const state = dragStateRef.current
    if (state?.dragging && !state.zooming) {
      updateSeekFromPointer(event.clientX, state.rulerLeft)
    }
    stopWindowDrag()
  }

  const onMouseDown = (event: React.MouseEvent<HTMLDivElement>) => {
    event.preventDefault()
    const rect = event.currentTarget.getBoundingClientRect()
    dragStateRef.current = {
      dragging: true,
      startY: event.clientY,
      lastStep: 0,
      rulerLeft: rect.left,
      zooming: false,
    }
    updateSeekFromPointer(event.clientX, rect.left)
    window.addEventListener('mousemove', onWindowMouseMove)
    window.addEventListener('mouseup', onWindowMouseUp)
  }

  return (
    <div
      className="ruler-click-overlay"
      style={{ left: controlsWidth }}
      onMouseDown={onMouseDown}
    />
  )
}

function PlaylistToolbar() {
  const controls = usePlaylistControls()
  const state = usePlaylistState()
  const data = usePlaylistData()
  const { splitClipAtPlayhead } = useClipSplitting({
    tracks: data.tracks,
    samplesPerPixel: data.samplesPerPixel,
    engineRef: data.playoutRef,
  })

  return (
    <div className="playlist-toolbar">
      <div className="tool-group">
        <button type="button" className="icon-button" onClick={() => void controls.play()}>
          <Play size={17} />
        </button>
        <button type="button" className="icon-button" onClick={controls.pause}>
          <Pause size={17} />
        </button>
        <button type="button" className="icon-button" onClick={controls.stop}>
          <Square size={15} />
        </button>
      </div>

      <div className="tool-group">
        <button
          type="button"
          className="icon-button"
          disabled={!state.canUndo}
          onClick={controls.undo}
        >
          <Undo2 size={17} />
        </button>
        <button
          type="button"
          className="icon-button"
          disabled={!state.canRedo}
          onClick={controls.redo}
        >
          <Redo2 size={17} />
        </button>
        <button type="button" className="icon-button" onClick={splitClipAtPlayhead}>
          <Scissors size={16} />
        </button>
      </div>

      <div className="tool-group">
        <button
          type="button"
          className="icon-button"
          disabled={!data.canZoomOut}
          onClick={controls.zoomOut}
        >
          <ZoomOut size={17} />
        </button>
        <button
          type="button"
          className="icon-button"
          disabled={!data.canZoomIn}
          onClick={controls.zoomIn}
        >
          <ZoomIn size={17} />
        </button>
      </div>

      <label className="volume-control">
        <Volume2 size={16} />
        <input
          type="range"
          min="0"
          max="1"
          step="0.01"
          value={data.masterVolume}
          onChange={(event) => controls.setMasterVolume(Number(event.currentTarget.value))}
        />
      </label>

      <span className="load-state">ready</span>
    </div>
  )
}

function TrackControls({ trackIndex }: { trackIndex: number }) {
  const controls = usePlaylistControls()
  const data = usePlaylistData()
  const playback = usePlaybackAnimation()
  const { soloPlayback, setSoloPlayback } = useSoloPlayback()
  const track = data.tracks[trackIndex]
  const trackState = data.trackStates[trackIndex]

  if (!trackState || !track) {
    return null
  }

  const isSoloPlaybackActive = soloPlayback?.trackIndex === trackIndex
  const restoreSoloStates = (soloedStates: boolean[]) => {
    soloedStates.forEach((soloed, index) => {
      controls.setTrackSolo(index, soloed)
    })
  }

  const handleSoloPlayback = async (event: React.MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation()

    if (soloPlayback?.trackIndex === trackIndex) {
      controls.stop()
      controls.setCurrentTime(soloPlayback.startTime)
      restoreSoloStates(soloPlayback.soloedStates)
      setSoloPlayback(null)
      return
    }

    const startTime = soloPlayback ? soloPlayback.startTime : playback.currentTimeRef.current ?? 0
    const soloedStates = soloPlayback?.soloedStates ?? data.trackStates.map((state) => state.soloed)
    controls.stop()
    controls.setCurrentTime(startTime)

    data.trackStates.forEach((_, index) => {
      controls.setTrackSolo(index, index === trackIndex)
    })

    setSoloPlayback({ trackIndex, startTime, soloedStates })
    await controls.play(startTime)
  }

  return (
    <div className="track-controls">
      <div className="track-header-row">
        <strong>{trackState.name || track.name}</strong>
      </div>
      <button
        type="button"
        className={trackState.soloed ? 'track-toggle active' : 'track-toggle'}
        onClick={() => controls.setTrackSolo(trackIndex, !trackState.soloed)}
      >
        S
      </button>
      <div className="track-mute-row">
        <button
          type="button"
          className={trackState.muted ? 'track-toggle active' : 'track-toggle'}
          onClick={() => controls.setTrackMute(trackIndex, !trackState.muted)}
        >
          M
        </button>
        <button
          type="button"
          className={isSoloPlaybackActive ? 'track-solo-play active' : 'track-solo-play'}
          onClick={(event) => void handleSoloPlayback(event)}
          title="このトラックだけ再生"
        >
          <Play size={14} />
          <span>S</span>
        </button>
      </div>
      <label className="track-volume">
        <span>VOL</span>
        <input
          aria-label={`${trackState.name} volume`}
          type="range"
          min="0"
          max="1"
          step="0.01"
          value={trackState.volume}
          onChange={(event) =>
            controls.setTrackVolume(trackIndex, Number(event.currentTarget.value))
          }
        />
      </label>
    </div>
  )
}

export default App
