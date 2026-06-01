import { useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle,
  FileAudio2,
  Link,
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

          <div className="track-list">
            {session.tracks.map((track) => (
              <article className="track-row" key={track.id}>
                <div className="track-icon">
                  <FileAudio2 size={22} />
                </div>
                <div className="track-body">
                  <div className="track-title">
                    <strong>{track.name}</strong>
                    <span>ID {track.id}</span>
                  </div>
                  <dl>
                    <div>
                      <dt>sourcePath</dt>
                      <dd>{track.sourcePath}</dd>
                    </div>
                    <div>
                      <dt>url</dt>
                      <dd>
                        <Link size={14} />
                        {track.url}
                      </dd>
                    </div>
                  </dl>
                  <audio controls preload="metadata" src={track.url} />
                </div>
              </article>
            ))}
          </div>
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

  return (
    <WaveformPlaylistProvider
      tracks={playlistTracks}
      onTracksChange={setPlaylistTracks}
      timescale
      waveHeight={76}
      samplesPerPixel={2048}
      controls={{ show: false, width: 0 }}
    >
      <KeyboardShortcuts playback clipSplitting undo />
      <PlaylistToolbar />
      <ClipInteractionProvider>
        <div className="playlist-view">
          <Waveform
            showClipHeaders
            showFades
            renderTrackControls={(trackIndex) => <TrackControls trackIndex={trackIndex} />}
          />
        </div>
      </ClipInteractionProvider>
    </WaveformPlaylistProvider>
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
  const trackState = data.trackStates[trackIndex]

  if (!trackState) {
    return null
  }

  return (
    <div className="track-controls">
      <button
        type="button"
        className={trackState.soloed ? 'track-toggle active' : 'track-toggle'}
        onClick={() => controls.setTrackSolo(trackIndex, !trackState.soloed)}
      >
        S
      </button>
      <button
        type="button"
        className={trackState.muted ? 'track-toggle active' : 'track-toggle'}
        onClick={() => controls.setTrackMute(trackIndex, !trackState.muted)}
      >
        M
      </button>
      <input
        aria-label={`${trackState.name} volume`}
        type="range"
        min="0"
        max="1"
        step="0.01"
        value={trackState.volume}
        onChange={(event) => controls.setTrackVolume(trackIndex, Number(event.currentTarget.value))}
      />
    </div>
  )
}

export default App
