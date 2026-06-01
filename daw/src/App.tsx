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

const SoloPlaybackContext = createContext<SoloPlaybackContextValue | null>(null)

function useSoloPlayback() {
  const context = useContext(SoloPlaybackContext)
  if (!context) {
    throw new Error('SoloPlaybackContext が見つかりません')
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
        <ClipInteractionProvider>
          <div ref={viewportRef} className="playlist-view">
            <RulerClickOverlay viewportRef={viewportRef} />
            <Waveform
              showClipHeaders
              showFades
              renderTrackControls={(trackIndex) => <TrackControls trackIndex={trackIndex} />}
            />
          </div>
        </ClipInteractionProvider>
      </SoloPlaybackContext.Provider>
    </WaveformPlaylistProvider>
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
          <span>S</span>
          <Play size={14} />
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
