import {
  createContext,
  type Dispatch,
  type SetStateAction,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import {
  AlertTriangle,
  AudioLines,
  ChevronDown,
  ChevronUp,
  Download,
  Infinity as InfinityIcon,
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
  Wrench,
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
import { createPortal } from 'react-dom'
import { Layers, SlidersHorizontal } from 'lucide-react'
import { useSilenceSplit } from './useSilenceSplit'
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
  singleTrack?: boolean
}

type SoloStateContextValue = {
  soloedTrackIndex: number | null
  setSoloedTrackIndex: Dispatch<SetStateAction<number | null>>
}

const SoloStateContext = createContext<SoloStateContextValue | null>(null)

function useSoloState() {
  const context = useContext(SoloStateContext)
  if (!context) {
    throw new Error('SoloStateContext が見つかりません')
  }
  return context
}

// === リージョン（コンピング）機能 ===

type DawMode = 'daw' | 'comping'

type Region = {
  id: string
  trackIndex: number
  start: number
  end: number
}

type DawExportOptions = {
  filename: string
  format: 'wav' | 'flac'
  saveMode: 'save' | 'download'
}

type AafExportClip = {
  name: string
  sourcePath: string
  timelineStart: number
  sourceStart: number
  duration: number
}

type AafExportTrack = {
  name: string
  clips: AafExportClip[]
}

type AafExportPayload = {
  sampleRate: number
  tracks: AafExportTrack[]
}

type DawModeContextValue = {
  mode: DawMode
  setMode: Dispatch<SetStateAction<DawMode>>
  allowOverlap: boolean
  setAllowOverlap: Dispatch<SetStateAction<boolean>>
}

type RegionContextValue = {
  regions: Region[]
  setRegions: Dispatch<SetStateAction<Region[]>>
  selectedRegionId: string | null
  setSelectedRegionId: Dispatch<SetStateAction<string | null>>
}

const DawModeContext = createContext<DawModeContextValue | null>(null)
const RegionContext = createContext<RegionContextValue | null>(null)

function useDawMode() {
  const context = useContext(DawModeContext)
  if (!context) {
    throw new Error('DawModeContext が見つかりません')
  }
  return context
}

function useRegions() {
  const context = useContext(RegionContext)
  if (!context) {
    throw new Error('RegionContext が見つかりません')
  }
  return context
}

// クリップヘッダの高さ（ui-components の CLIP_HEADER_HEIGHT）
const CLIP_HEADER_HEIGHT = 22
// リージョン矩形が覆うクリップ本体の縦割合（上部のみ覆い、下部はシーク用に空ける）
const REGION_HEIGHT_RATIO = 0.8
// リサイズハンドルの当たり幅（ピクセル）
const REGION_RESIZE_HANDLE_PX = 6
// 作成ドラッグとクリック（シーク）を分ける移動量しきい値（ピクセル）
const REGION_DRAG_THRESHOLD_PX = 3
// 重なり解消でこの秒数未満になったリージョンは削除する
const REGION_MIN_DURATION = 0.02

function makeRegionId(): string {
  return `region-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

function loadRegions(key: string): Region[] {
  try {
    const raw = window.sessionStorage.getItem(key)
    if (!raw) {
      return []
    }

    const value = JSON.parse(raw)
    if (!Array.isArray(value)) {
      return []
    }

    return value
      .filter(
        (item): item is Region =>
          item &&
          typeof item.id === 'string' &&
          typeof item.trackIndex === 'number' &&
          typeof item.start === 'number' &&
          typeof item.end === 'number',
      )
      .map((item) => ({
        id: item.id,
        trackIndex: item.trackIndex,
        start: item.start,
        end: item.end,
      }))
  } catch {
    return []
  }
}

/**
 * ステップ1: ドラッグ中の同一トラッククランプ。
 * 操作中リージョンが同一トラックの他リージョンにぶつかったら、ぶつかる方向へは伸ばさない。
 * proposedStart/End は秒。edge は伸ばそうとしている向きの判定に使う。
 */
function clampToSameTrack(
  regions: Region[],
  trackIndex: number,
  activeId: string | null,
  proposedStart: number,
  proposedEnd: number,
): { start: number; end: number } {
  let start = proposedStart
  let end = proposedEnd

  for (const other of regions) {
    if (other.id === activeId || other.trackIndex !== trackIndex) {
      continue
    }
    // 完全に分離しているなら無視
    if (other.end <= start || other.start >= end) {
      continue
    }
    // 重なっている: 操作中の中心から見て、相手が右ならend、左ならstartをクランプ
    const activeCenter = (start + end) / 2
    const otherCenter = (other.start + other.end) / 2
    if (otherCenter >= activeCenter) {
      // 相手は右側 → end を相手の手前まで
      end = Math.min(end, other.start)
    } else {
      // 相手は左側 → start を相手の後ろまで
      start = Math.max(start, other.end)
    }
  }

  if (end < start) {
    end = start
  }
  return { start, end }
}

/**
 * ステップ2: 確定後の重なり解消（allowOverlap オフ時のみ呼ぶ）。
 * active 以外で active と重なるリージョンを削る／完全内包は削除／幅が極小なら削除。
 * allowOverlap オフでは他トラックも対象（呼び出し側で対象トラックを絞らず全件渡す）。
 */
function resolveOverlapsAfterCommit(regions: Region[], active: Region): Region[] {
  const result: Region[] = []

  for (const other of regions) {
    if (other.id === active.id) {
      result.push(other)
      continue
    }
    // 分離しているならそのまま
    if (other.end <= active.start || other.start >= active.end) {
      result.push(other)
      continue
    }
    // active が other を完全内包 → 削除
    if (active.start <= other.start && active.end >= other.end) {
      continue
    }
    // other が active を完全内包 → other を active の前後に分割
    if (other.start < active.start && other.end > active.end) {
      const left: Region = { ...other, end: active.start }
      const right: Region = {
        ...other,
        id: `${other.id}-r`,
        start: active.end,
      }
      if (left.end - left.start >= REGION_MIN_DURATION) {
        result.push(left)
      }
      if (right.end - right.start >= REGION_MIN_DURATION) {
        result.push(right)
      }
      continue
    }
    // 部分重なり: other を active と重ならないよう削る
    let trimmed: Region
    if (other.start < active.start) {
      trimmed = { ...other, end: active.start }
    } else {
      trimmed = { ...other, start: active.end }
    }
    if (trimmed.end - trimmed.start >= REGION_MIN_DURATION) {
      result.push(trimmed)
    }
  }

  return result
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
        </div>
        <button type="button" className="toolbar-button" onClick={reloadSession}>
          <RefreshCw size={17} />
          再読み込み （変更は破棄されます）
        </button>
      </header>


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

          <PlaylistArea sourceTracks={session.tracks} singleTrack={session.singleTrack ?? false} />
        </section>
      )}

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

    </main>
  )
}

function PlaylistArea({ sourceTracks, singleTrack }: { sourceTracks: DawTrack[]; singleTrack: boolean }) {
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
  const { tracks: rawTracks, loading, error, loadedCount, totalCount } = useAudioTracks(configs)

  // シングルトラックモード: 全クリップを1本の ClipTrack にまとめる
  const tracks = useMemo((): ClipTrack[] => {
    if (!singleTrack || rawTracks.length === 0) return rawTracks
    const allClips = rawTracks.flatMap((t) => t.clips)
    const first = rawTracks[0]
    const merged: ClipTrack = {
      ...first,
      id: first.id,
      name: sourceTracks[0]?.name ?? first.name,
      clips: allClips,
    }
    return [merged]
  }, [singleTrack, rawTracks, sourceTracks])

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
        <EditablePlaylist
          key={sourceTracks.map((track) => track.id).join(':')}
          initialTracks={tracks}
          sourceTracks={sourceTracks}
        />
      )}
    </div>
  )
}

type TrackHeightMode = 'large' | 'small'

const TRACK_CONTROLS_WIDTH = 200
const WAVE_HEIGHT_LARGE = 76
const WAVE_HEIGHT_SMALL = 38

function getSelectionRange(selectionStart: number, selectionEnd: number) {
  const start = Math.min(selectionStart, selectionEnd)
  const end = Math.max(selectionStart, selectionEnd)
  return end > start ? { start, end } : null
}

function getLoopRange(loopStart: number, loopEnd: number) {
  const start = Math.min(loopStart, loopEnd)
  const end = Math.max(loopStart, loopEnd)
  return end > start ? { start, end } : null
}

function getLoopAwarePlayStart(
  currentTime: number,
  loopRange: { start: number; end: number } | null,
  isLoopEnabled: boolean,
) {
  if (!isLoopEnabled || !loopRange) {
    return currentTime
  }
  return currentTime >= loopRange.start && currentTime < loopRange.end
    ? currentTime
    : loopRange.start
}

function filenameWithoutExtension(name: string) {
  return name.replace(/\.[^/.]+$/, '') || 'daw-export'
}

function writeAscii(view: DataView, offset: number, value: string) {
  for (let i = 0; i < value.length; i += 1) {
    view.setUint8(offset + i, value.charCodeAt(i))
  }
}

function encodeWavBuffer(channels: Float32Array[], sampleRate: number) {
  const bitDepth = 16
  const bytesPerSample = bitDepth / 8
  const channelCount = channels.length
  const sampleCount = channels[0]?.length ?? 0
  const blockAlign = channelCount * bytesPerSample
  const byteRate = sampleRate * blockAlign
  const dataSize = sampleCount * blockAlign
  const buffer = new ArrayBuffer(44 + dataSize)
  const view = new DataView(buffer)

  writeAscii(view, 0, 'RIFF')
  view.setUint32(4, 36 + dataSize, true)
  writeAscii(view, 8, 'WAVE')
  writeAscii(view, 12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, channelCount, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, byteRate, true)
  view.setUint16(32, blockAlign, true)
  view.setUint16(34, bitDepth, true)
  writeAscii(view, 36, 'data')
  view.setUint32(40, dataSize, true)

  let offset = 44
  for (let i = 0; i < sampleCount; i += 1) {
    for (let ch = 0; ch < channelCount; ch += 1) {
      const sample = Math.max(-1, Math.min(1, channels[ch][i] ?? 0))
      const intSample = sample < 0 ? sample * 0x8000 : sample * 0x7fff
      view.setInt16(offset, intSample, true)
      offset += 2
    }
  }

  return buffer
}

function isSampleInRanges(sample: number, ranges: Array<{ start: number; end: number }>) {
  return ranges.some((range) => sample >= range.start && sample < range.end)
}

type RenderClip = {
  audioBuffer?: AudioBuffer
  startSample?: number
  durationSamples?: number
  offsetSamples?: number
  sampleRate?: number
  gain?: number
  fadeIn?: { duration?: number }
  fadeOut?: { duration?: number }
}

type RenderTrack = {
  clips?: RenderClip[]
}

function asRenderTrack(track: ClipTrack): RenderTrack {
  return track as unknown as RenderTrack
}

function clipFadeGain(clip: RenderClip, clipTime: number, fallbackSampleRate: number) {
  let gain = Number(clip.gain ?? 1)
  const fadeInDuration = Number(clip.fadeIn?.duration ?? 0)
  if (fadeInDuration > 0 && clipTime < fadeInDuration) {
    gain *= Math.max(0, Math.min(1, clipTime / fadeInDuration))
  }
  const clipDuration = Number(clip.durationSamples ?? 0) / Number(clip.sampleRate ?? fallbackSampleRate)
  const fadeOutDuration = Number(clip.fadeOut?.duration ?? 0)
  if (fadeOutDuration > 0 && clipTime > clipDuration - fadeOutDuration) {
    gain *= Math.max(0, Math.min(1, (clipDuration - clipTime) / fadeOutDuration))
  }
  return gain
}

function renderPlaylistWav(params: {
  tracks: ClipTrack[]
  trackStates: Array<{ muted: boolean; soloed: boolean; volume: number; pan?: number }>
  regions: Region[]
  mode: DawMode
  soloedTrackIndex: number | null
  sampleRate: number
}) {
  const { tracks, trackStates, regions, mode, soloedTrackIndex, sampleRate } = params
  const paddingSamples = Math.round(sampleRate * 0.1)
  let totalSamples = paddingSamples
  let outputChannels = 1

  tracks.forEach((track) => {
    asRenderTrack(track).clips?.forEach((clip) => {
      totalSamples = Math.max(
        totalSamples,
        Number(clip.startSample ?? 0) + Number(clip.durationSamples ?? 0) + paddingSamples,
      )
      outputChannels = Math.max(outputChannels, Number(clip.audioBuffer?.numberOfChannels ?? 1))
    })
  })
  if (trackStates.some((state) => Math.abs(Number(state.pan ?? 0)) > 0.001)) {
    outputChannels = Math.max(outputChannels, 2)
  }

  const output = Array.from({ length: outputChannels }, () => new Float32Array(totalSamples))
  const hasSoloState = soloedTrackIndex !== null || trackStates.some((state) => state.soloed)
  const regionRangesByTrack = new Map<number, Array<{ start: number; end: number }>>()
  if (mode === 'comping') {
    regions.forEach((region) => {
      const ranges = regionRangesByTrack.get(region.trackIndex) ?? []
      ranges.push({
        start: Math.round(region.start * sampleRate),
        end: Math.round(region.end * sampleRate),
      })
      regionRangesByTrack.set(region.trackIndex, ranges)
    })
  }

  tracks.forEach((track, trackIndex) => {
    const state = trackStates[trackIndex]
    if (!state || state.muted) return
    if (soloedTrackIndex !== null && soloedTrackIndex !== trackIndex) return
    if (soloedTrackIndex === null && hasSoloState && !state.soloed) return

    const trackVolume = Number(state.volume ?? 1)
    const pan = Math.max(-1, Math.min(1, Number(state.pan ?? 0)))
    const gateRanges = regionRangesByTrack.get(trackIndex) ?? []

    asRenderTrack(track).clips?.forEach((clip) => {
      const audioBuffer = clip.audioBuffer
      if (!audioBuffer) return
      const sourceChannels = audioBuffer.numberOfChannels
      const startSample = Number(clip.startSample ?? 0)
      const durationSamples = Number(clip.durationSamples ?? 0)
      const offsetSamples = Number(clip.offsetSamples ?? 0)

      for (let i = 0; i < durationSamples; i += 1) {
        const destSample = startSample + i
        if (destSample < 0 || destSample >= totalSamples) continue
        if (
          mode === 'comping' &&
          soloedTrackIndex === null &&
          !isSampleInRanges(destSample, gateRanges)
        ) {
          continue
        }

        const srcSample = offsetSamples + i
        if (srcSample < 0 || srcSample >= audioBuffer.length) continue
        const clipTime = i / sampleRate
        const gain = trackVolume * clipFadeGain(clip, clipTime, sampleRate)

        if (outputChannels === 1) {
          let mixed = 0
          for (let ch = 0; ch < sourceChannels; ch += 1) {
            mixed += audioBuffer.getChannelData(ch)[srcSample] ?? 0
          }
          output[0][destSample] += (mixed / sourceChannels) * gain
        } else {
          const leftSource = audioBuffer.getChannelData(0)[srcSample] ?? 0
          const rightSource =
            sourceChannels > 1 ? audioBuffer.getChannelData(1)[srcSample] ?? 0 : leftSource
          const leftGain = pan <= 0 ? 1 : 1 - pan
          const rightGain = pan >= 0 ? 1 : 1 + pan
          output[0][destSample] += leftSource * gain * leftGain
          output[1][destSample] += rightSource * gain * rightGain
        }
      }
    })
  })

  return encodeWavBuffer(output, sampleRate)
}

function buildAafExportPayload(params: {
  tracks: ClipTrack[]
  sourceByTrackId: Map<string, DawTrack>
  regions: Region[]
  mode: DawMode
  sampleRate: number
}): AafExportPayload {
  const { tracks, sourceByTrackId, regions, mode, sampleRate } = params

  return {
    sampleRate,
    tracks: tracks.map((track, trackIndex) => {
      const source = sourceByTrackId.get(track.id)
      const sourcePath = source?.sourcePath ?? track.name
      const clips = asRenderTrack(track).clips ?? []

      if (mode !== 'comping') {
        return {
          name: track.name,
          clips: clips.map((clip) => ({
            name: clipName(clip, track.name),
            sourcePath,
            timelineStart: Number(clip.startSample ?? 0) / sampleRate,
            sourceStart: Number(clip.offsetSamples ?? 0) / sampleRate,
            duration: Number(clip.durationSamples ?? 0) / sampleRate,
          })),
        }
      }

      const regionClips: AafExportClip[] = []
      const trackRegions = regions
        .filter((region) => region.trackIndex === trackIndex)
        .sort((a, b) => a.start - b.start)

      trackRegions.forEach((region) => {
        clips.forEach((clip) => {
          const clipStart = Number(clip.startSample ?? 0) / sampleRate
          const clipDuration = Number(clip.durationSamples ?? 0) / sampleRate
          const clipEnd = clipStart + clipDuration
          const start = Math.max(region.start, clipStart)
          const end = Math.min(region.end, clipEnd)
          if (end - start < REGION_MIN_DURATION) {
            return
          }
          const sourceStart = Number(clip.offsetSamples ?? 0) / sampleRate + (start - clipStart)
          regionClips.push({
            name: `${clipName(clip, track.name)} (${region.start.toFixed(2)}-${region.end.toFixed(2)})`,
            sourcePath,
            timelineStart: start,
            sourceStart,
            duration: end - start,
          })
        })
      })

      return {
        name: track.name,
        clips: regionClips,
      }
    }),
  }
}

function clipName(clip: RenderClip, fallback: string) {
  return String((clip as { name?: string }).name || fallback)
}

function EditablePlaylist({
  initialTracks,
  sourceTracks,
}: {
  initialTracks: ClipTrack[]
  sourceTracks: DawTrack[]
}) {
  const regionStorageKey = useMemo(() => {
    const session = new URLSearchParams(window.location.search).get('session') ?? 'default'
    return `dataset-ui:daw:regions:${session}`
  }, [])
  const [playlistTracks, setPlaylistTracks] = useState(initialTracks)
  const [soloedTrackIndex, setSoloedTrackIndex] = useState<number | null>(null)
  const [mode, setMode] = useState<DawMode>('daw')
  const [allowOverlap, setAllowOverlap] = useState(false)
  const [trackHeightMode, setTrackHeightMode] = useState<TrackHeightMode>('large')
  const [regions, setRegions] = useState<Region[]>(() => loadRegions(regionStorageKey))
  const [selectedRegionId, setSelectedRegionId] = useState<string | null>(null)
  const viewportRef = useRef<HTMLDivElement | null>(null)
  const waveHeight = trackHeightMode === 'small' ? WAVE_HEIGHT_SMALL : WAVE_HEIGHT_LARGE
  const sourceByTrackId = useMemo(() => {
    const map = new Map<string, DawTrack>()
    initialTracks.forEach((track, index) => {
      const source = sourceTracks[index]
      if (source) {
        map.set(track.id, source)
      }
    })
    return map
  }, [initialTracks, sourceTracks])

  const moveTrack = (trackIndex: number, direction: -1 | 1) => {
    const nextIndex = trackIndex + direction
    if (nextIndex < 0 || nextIndex >= playlistTracks.length) {
      return
    }

    setPlaylistTracks((current) => {
      if (trackIndex >= current.length || nextIndex >= current.length) {
        return current
      }
      const next = [...current]
      const moving = next[trackIndex]
      next[trackIndex] = next[nextIndex]
      next[nextIndex] = moving
      return next
    })
    setRegions((current) =>
      current.map((region) => {
        if (region.trackIndex === trackIndex) {
          return { ...region, trackIndex: nextIndex }
        }
        if (region.trackIndex === nextIndex) {
          return { ...region, trackIndex }
        }
        return region
      }),
    )
    setSoloedTrackIndex((current) => {
      if (current === trackIndex) return nextIndex
      if (current === nextIndex) return trackIndex
      return current
    })
  }

  useEffect(() => {
    window.sessionStorage.setItem(regionStorageKey, JSON.stringify(regions))
  }, [regions, regionStorageKey])

  const lockClipEditing = mode === 'comping' && !allowOverlap

  const focusClipHandle = (event: React.MouseEvent<HTMLDivElement>) => {
    if (lockClipEditing) {
      return
    }
    const target = event.target
    if (!(target instanceof HTMLElement)) {
      return
    }

    const handle = target.closest('[aria-roledescription="draggable"]')
    if (handle instanceof HTMLElement) {
      viewportRef.current
        ?.querySelectorAll('.clip-focus-visible')
        .forEach((element) => element.classList.remove('clip-focus-visible'))
      handle.classList.add('clip-focus-visible')
      handle.focus()
      // クリップを選択したらリージョン選択を解除する
      setSelectedRegionId(null)
    }
  }

  return (
    <WaveformPlaylistProvider
      tracks={playlistTracks}
      onTracksChange={setPlaylistTracks}
      timescale
      waveHeight={waveHeight}
      samplesPerPixel={2048}
      controls={{ show: true, width: TRACK_CONTROLS_WIDTH }}
    >
      <KeyboardShortcuts clipSplitting undo />
      <PlaybackKeyboard />
      <DawModeContext.Provider value={{ mode, setMode, allowOverlap, setAllowOverlap }}>
        <RegionContext.Provider
          value={{ regions, setRegions, selectedRegionId, setSelectedRegionId }}
        >
          <PlaylistToolbar
            trackHeightMode={trackHeightMode}
            setTrackHeightMode={setTrackHeightMode}
          />
          <SoloStateContext.Provider value={{ soloedTrackIndex, setSoloedTrackIndex }}>
            <ExportBridge sourceByTrackId={sourceByTrackId} />
            {lockClipEditing ? (
              <PlaylistView
                viewportRef={viewportRef}
                focusClipHandle={focusClipHandle}
                trackHeightMode={trackHeightMode}
                playlistTrackCount={playlistTracks.length}
                moveTrack={moveTrack}
                mode={mode}
              />
            ) : (
              <ClipInteractionProvider>
                <PlaylistView
                  viewportRef={viewportRef}
                  focusClipHandle={focusClipHandle}
                  trackHeightMode={trackHeightMode}
                  playlistTrackCount={playlistTracks.length}
                  moveTrack={moveTrack}
                  mode={mode}
                />
              </ClipInteractionProvider>
            )}
            {mode === 'comping' && <RegionPlaybackGate />}
            {mode === 'comping' && <RegionKeyboard />}
          </SoloStateContext.Provider>
        </RegionContext.Provider>
      </DawModeContext.Provider>
    </WaveformPlaylistProvider>
  )
}

function PlaylistView({
  viewportRef,
  focusClipHandle,
  trackHeightMode,
  playlistTrackCount,
  moveTrack,
  mode,
}: {
  viewportRef: React.RefObject<HTMLDivElement | null>
  focusClipHandle: (event: React.MouseEvent<HTMLDivElement>) => void
  trackHeightMode: TrackHeightMode
  playlistTrackCount: number
  moveTrack: (trackIndex: number, direction: -1 | 1) => void
  mode: DawMode
}) {
  return (
    <div
      ref={viewportRef}
      className="playlist-view"
      onMouseDownCapture={focusClipHandle}
    >
      <RulerClickOverlay viewportRef={viewportRef} />
      <Waveform
        showClipHeaders
        showFades
        renderTrackControls={(trackIndex) => (
          <TrackControls
            trackIndex={trackIndex}
            trackHeightMode={trackHeightMode}
            canMoveUp={trackIndex > 0}
            canMoveDown={trackIndex < playlistTrackCount - 1}
            onMoveTrack={moveTrack}
          />
        )}
      />
      {mode === 'comping' && (
        <RegionOverlay
          viewportRef={viewportRef}
          layoutKey={trackHeightMode}
        />
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

function PlaylistToolbar({
  trackHeightMode,
  setTrackHeightMode,
}: {
  trackHeightMode: TrackHeightMode
  setTrackHeightMode: Dispatch<SetStateAction<TrackHeightMode>>
}) {
  const controls = usePlaylistControls()
  const state = usePlaylistState()
  const data = usePlaylistData()
  const playback = usePlaybackAnimation()
  const selectionRange = getSelectionRange(state.selectionStart, state.selectionEnd)
  const loopRange = getLoopRange(state.loopStart, state.loopEnd)
  const canToggleLoop = Boolean(selectionRange || loopRange)
  const [exportMenuOpen, setExportMenuOpen] = useState(false)
  const exportMenuRef = useRef<HTMLDivElement | null>(null)
  const [toolMenuOpen, setToolMenuOpen] = useState(false)
  const toolMenuRef = useRef<HTMLDivElement | null>(null)
  const { splitClipAtPlayhead } = useClipSplitting({
    tracks: data.tracks,
    samplesPerPixel: data.samplesPerPixel,
    engineRef: data.playoutRef,
  })
  const splitOnSilence = useSilenceSplit()
  const playFromCurrentState = () => {
    const currentTime = playback.currentTimeRef.current ?? 0
    const startTime = getLoopAwarePlayStart(currentTime, loopRange, state.isLoopEnabled)
    if (startTime !== currentTime) {
      controls.setCurrentTime(startTime)
    }
    void controls.play(startTime)
  }
  const toggleLoopPlayback = () => {
    if (selectionRange) {
      controls.setLoopRegion(selectionRange.start, selectionRange.end)
      if (!state.isLoopEnabled) {
        controls.setLoopEnabled(true)
      }
      controls.setSelection(0, 0)
      return
    }
    if (loopRange) {
      controls.setLoopEnabled(!state.isLoopEnabled)
    }
  }
  const requestExport = (saveMode: DawExportOptions['saveMode']) => {
    setExportMenuOpen(false)
    const defaultFilename = filenameWithoutExtension(data.tracks[0]?.name ?? 'daw-export')
    window.parent.postMessage(
      {
        type: 'daw-export-request',
        requestId: `export-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        sessionId: new URLSearchParams(window.location.search).get('session') ?? '',
        defaultFilename,
        saveMode,
      },
      '*',
    )
  }
  const requestAafExport = (saveMode: DawExportOptions['saveMode']) => {
    setExportMenuOpen(false)
    window.parent.postMessage(
      {
        type: 'daw-aaf-export-request',
        requestId: `aaf-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        sessionId: new URLSearchParams(window.location.search).get('session') ?? '',
        defaultFilename: filenameWithoutExtension(data.tracks[0]?.name ?? 'daw-edit'),
        saveMode,
      },
      '*',
    )
  }
  useEffect(() => {
    if (!exportMenuOpen) {
      return
    }

    const onDocumentMouseDown = (event: MouseEvent) => {
      if (
        exportMenuRef.current &&
        event.target instanceof Node &&
        exportMenuRef.current.contains(event.target)
      ) {
        return
      }
      setExportMenuOpen(false)
    }

    document.addEventListener('mousedown', onDocumentMouseDown)
    return () => document.removeEventListener('mousedown', onDocumentMouseDown)
  }, [exportMenuOpen])

  useEffect(() => {
    if (!toolMenuOpen) {
      return
    }

    const onDocumentMouseDown = (event: MouseEvent) => {
      if (
        toolMenuRef.current &&
        event.target instanceof Node &&
        toolMenuRef.current.contains(event.target)
      ) {
        return
      }
      setToolMenuOpen(false)
    }

    document.addEventListener('mousedown', onDocumentMouseDown)
    return () => document.removeEventListener('mousedown', onDocumentMouseDown)
  }, [toolMenuOpen])

  return (
    <div className="playlist-toolbar">
      <div className="tool-group">
        <button type="button" className="icon-button" onClick={playFromCurrentState}>
          <Play size={17} />
        </button>
        <button type="button" className="icon-button" onClick={controls.pause}>
          <Pause size={17} />
        </button>
        <button type="button" className="icon-button" onClick={controls.stop}>
          <Square size={15} />
        </button>
        <button
          type="button"
          className={state.isLoopEnabled ? 'icon-button active' : 'icon-button'}
          disabled={!canToggleLoop}
          title="ループ再生切替 (L)"
          onClick={toggleLoopPlayback}
        >
          <InfinityIcon size={17} />
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
        <div className="export-menu" ref={toolMenuRef}>
          <button
            type="button"
            className="text-button"
            onClick={() => setToolMenuOpen((current) => !current)}
          >
            <Wrench size={15} />
            ツール
          </button>
          <div className={toolMenuOpen ? 'export-menu-list open' : 'export-menu-list'}>
            <button
              type="button"
              title="-60dBのしきい値で分割します"
              onClick={() => {
                setToolMenuOpen(false)
                splitOnSilence()
              }}
            >
              <AudioLines size={14} />
              無音区間で分割
            </button>
          </div>
        </div>
        <div className="export-menu" ref={exportMenuRef}>
          <button
            type="button"
            className="text-button"
            onClick={() => setExportMenuOpen((current) => !current)}
          >
            <Download size={15} />
            書き出し
          </button>
          <div className={exportMenuOpen ? 'export-menu-list open' : 'export-menu-list'}>
            <button type="button" onClick={() => requestExport('save')}>
              書き出しフォルダに保存
            </button>
            <button type="button" onClick={() => requestExport('download')}>
              ダウンロード
            </button>
            <button type="button" onClick={() => requestAafExport('save')}>
              AAFを保存
            </button>
            <button type="button" onClick={() => requestAafExport('download')}>
              AAFをダウンロード
            </button>
          </div>
        </div>
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

      <TrackHeightToggle
        trackHeightMode={trackHeightMode}
        setTrackHeightMode={setTrackHeightMode}
      />

      <ModeToggle />

      <span className="load-state">ready</span>
    </div>
  )
}

function TrackHeightToggle({
  trackHeightMode,
  setTrackHeightMode,
}: {
  trackHeightMode: TrackHeightMode
  setTrackHeightMode: Dispatch<SetStateAction<TrackHeightMode>>
}) {
  return (
    <div className="height-toggle" onMouseDown={(event) => event.stopPropagation()}>
      <span>高さ</span>
      <div className="height-switch">
        <button
          type="button"
          className={trackHeightMode === 'large' ? 'height-button active' : 'height-button'}
          onClick={() => setTrackHeightMode('large')}
        >
          大
        </button>
        <button
          type="button"
          className={trackHeightMode === 'small' ? 'height-button active' : 'height-button'}
          onClick={() => setTrackHeightMode('small')}
        >
          小
        </button>
      </div>
    </div>
  )
}

function ExportBridge({ sourceByTrackId }: { sourceByTrackId: Map<string, DawTrack> }) {
  const data = usePlaylistData()
  const { regions } = useRegions()
  const { mode } = useDawMode()
  const { soloedTrackIndex } = useSoloState()

  const exportStateRef = useRef({
    tracks: data.tracks,
    trackStates: data.trackStates,
    sampleRate: data.sampleRate,
    regions,
    mode,
    soloedTrackIndex,
    sourceByTrackId,
  })

  useEffect(() => {
    exportStateRef.current = {
      tracks: data.tracks,
      trackStates: data.trackStates,
      sampleRate: data.sampleRate,
      regions,
      mode,
      soloedTrackIndex,
      sourceByTrackId,
    }
  }, [data.tracks, data.trackStates, data.sampleRate, regions, mode, soloedTrackIndex, sourceByTrackId])

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      const message = event.data
      if (!message) {
        return
      }
      if (message.type === 'daw-aaf-export-start') {
        const requestId = String(message.requestId ?? '')
        try {
          const current = exportStateRef.current
          const aaf = buildAafExportPayload({
            tracks: current.tracks,
            sourceByTrackId: current.sourceByTrackId,
            regions: current.regions,
            mode: current.mode,
            sampleRate: current.sampleRate,
          })
          window.parent.postMessage(
            {
              type: 'daw-aaf-export-data',
              requestId,
              options: message.options,
              aaf,
            },
            '*',
          )
        } catch (error) {
          window.parent.postMessage(
            {
              type: 'daw-export-error',
              requestId,
              message: error instanceof Error ? error.message : 'AAF 書き出しに失敗しました',
            },
            '*',
          )
        }
        return
      }
      if (message.type !== 'daw-export-start') {
        return
      }

      const options = message.options as DawExportOptions
      const requestId = String(message.requestId ?? '')
      try {
        const current = exportStateRef.current
        const wavBuffer = renderPlaylistWav({
          tracks: current.tracks,
          trackStates: current.trackStates,
          regions: current.regions,
          mode: current.mode,
          soloedTrackIndex: current.soloedTrackIndex,
          sampleRate: current.sampleRate,
        })
        window.parent.postMessage(
          {
            type: 'daw-export-audio',
            requestId,
            options,
            wavBuffer,
          },
          '*',
          [wavBuffer],
        )
      } catch (error) {
        window.parent.postMessage(
          {
            type: 'daw-export-error',
            requestId,
            message: error instanceof Error ? error.message : '書き出しに失敗しました',
          },
          '*',
        )
      }
    }

    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [])

  return null
}

function ModeToggle() {
  const { mode, setMode, allowOverlap, setAllowOverlap } = useDawMode()

  return (
    <div className="mode-toggle" onMouseDown={(event) => event.stopPropagation()}>
      <div className="mode-switch">
        <button
          type="button"
          className={mode === 'daw' ? 'mode-button active' : 'mode-button'}
          onClick={() => setMode('daw')}
        >
          <SlidersHorizontal size={14} />
          DAW
        </button>
        <button
          type="button"
          className={mode === 'comping' ? 'mode-button active' : 'mode-button'}
          onClick={() => setMode('comping')}
        >
          <Layers size={14} />
          コンピング
        </button>
      </div>
      <label
        className="overlap-control"
        style={{ visibility: mode === 'comping' ? 'visible' : 'hidden' }}
      >
        <input
          type="checkbox"
          checked={allowOverlap}
          onChange={(event) => setAllowOverlap(event.currentTarget.checked)}
        />
        重なり許容
      </label>
    </div>
  )
}

// トラックごとの縦レイアウト（viewport 内ローカル座標）
type TrackLayout = {
  trackIndex: number
  trackId: string
  top: number // クリップ本体上端（ヘッダ下）
  height: number // クリップ本体（波形）の高さ
}

/**
 * viewport 内の各トラック行の縦位置を実測する。
 * data-track-id は ChannelContainer（トラックごと1個）と ClipContainer（クリップごと）の両方に付く。
 * ClipContainer は data-clip-container="true" も持つので :not([data-clip-container]) で除外する。
 */
// baseEl: top 計算の基準要素（portal 挿入先）
function measureTrackLayouts(viewport: HTMLElement, baseEl?: HTMLElement): TrackLayout[] {
  const trackEls = Array.from(
    viewport.querySelectorAll<HTMLElement>('[data-track-id]:not([data-clip-container])'),
  )
  const base = baseEl ?? viewport
  const baseRect = base.getBoundingClientRect()

  return trackEls.map((el, index) => {
    const rect = el.getBoundingClientRect()
    const localTop = rect.top - baseRect.top + (baseEl ? baseEl.scrollTop : 0)
    return {
      trackIndex: index,
      trackId: el.dataset.trackId ?? '',
      top: localTop + CLIP_HEADER_HEIGHT,
      height: Math.max(0, rect.height - CLIP_HEADER_HEIGHT),
    }
  })
}

type RegionDragState =
  | {
      kind: 'create'
      trackIndex: number
      anchorTime: number // 始点（固定）
      startX: number
      startY: number
      moved: boolean
    }
  | {
      kind: 'move'
      regionId: string
      trackIndex: number
      grabOffset: number // 掴んだ位置 - region.start（秒）
      width: number // region 幅（秒、固定）
      startX: number
      moved: boolean
    }
  | {
      kind: 'resize'
      regionId: string
      trackIndex: number
      edge: 'start' | 'end'
      fixedTime: number // 反対端（固定）
      startX: number
    }

function clearClipFocus(viewportRef: React.RefObject<HTMLDivElement | null>) {
  viewportRef.current
    ?.querySelectorAll('.clip-focus-visible')
    .forEach((element) => element.classList.remove('clip-focus-visible'))
}

function RegionOverlay({
  viewportRef,
  layoutKey,
}: {
  viewportRef: React.RefObject<HTMLDivElement | null>
  layoutKey: TrackHeightMode
}) {
  const data = usePlaylistData()
  const controls = usePlaylistControls()
  const { regions, setRegions, selectedRegionId, setSelectedRegionId } = useRegions()
  const { allowOverlap } = useDawMode()

  // リージョンを選択するときにクリップのフォーカスも解除する
  const selectRegion = (id: string | null) => {
    setSelectedRegionId(id)
    if (id !== null) {
      clearClipFocus(viewportRef)
    }
  }

  const [layouts, setLayouts] = useState<TrackLayout[]>([])
  const dragRef = useRef<RegionDragState | null>(null)
  const [draftRegion, setDraftRegion] = useState<Region | null>(null)

  // 最新の値を window リスナから参照するための ref
  const stateRef = useRef({ regions, allowOverlap })
  useEffect(() => {
    stateRef.current = { regions, allowOverlap }
  }, [regions, allowOverlap])

  // portal 挿入先（ScrollArea）。スクロールするコンテナの中に絶対配置する。
  const scrollEl = controls.scrollContainerRef.current

  // ScrollArea 内の絶対ピクセル座標（スクロールを引かない）
  const timeToPixel = (time: number) =>
    (time * data.sampleRate) / data.samplesPerPixel

  const measureLayouts = () => {
    const viewport = viewportRef.current
    const base = controls.scrollContainerRef.current ?? undefined
    if (!viewport) return
    setLayouts(measureTrackLayouts(viewport, base))
  }

  useEffect(() => {
    measureLayouts()
    window.addEventListener('resize', measureLayouts)
    return () => window.removeEventListener('resize', measureLayouts)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    measureLayouts()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data.samplesPerPixel, data.tracks.length, data.duration])

  useEffect(() => {
    measureLayouts()
    const frame = window.requestAnimationFrame(measureLayouts)
    return () => window.cancelAnimationFrame(frame)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layoutKey])

  // clientX → タイムライン秒数（ScrollArea の left + scrollLeft を基準）
  const pixelToTime = (clientX: number) => {
    const el = controls.scrollContainerRef.current
    if (!el) return 0
    const rect = el.getBoundingClientRect()
    const waveformPixel = clientX - rect.left + el.scrollLeft
    const seconds = (Math.max(0, waveformPixel) * data.samplesPerPixel) / data.sampleRate
    return Math.max(0, Math.min(seconds, data.duration || seconds))
  }

  const commitActive = (active: Region) => {
    setRegions((current) => {
      // active を最新の幅で反映
      const withActive = current.some((r) => r.id === active.id)
        ? current.map((r) => (r.id === active.id ? active : r))
        : [...current, active]
      if (stateRef.current.allowOverlap) {
        return withActive
      }
      return resolveOverlapsAfterCommit(withActive, active)
    })
  }

  // drag 情報とマウス位置から、確定前リージョン（プレビュー兼確定値）を計算する。
  // State(draftRegion) に依存しないので window リスナのクロージャ陳腐化を受けない。
  const computeDraft = (drag: RegionDragState, clientX: number): Region => {
    const time = pixelToTime(clientX)

    if (drag.kind === 'create') {
      const rawStart = Math.min(drag.anchorTime, time)
      const rawEnd = Math.max(drag.anchorTime, time)
      const clamped = clampToSameTrack(
        stateRef.current.regions,
        drag.trackIndex,
        null,
        rawStart,
        rawEnd,
      )
      return {
        id: '__draft__',
        trackIndex: drag.trackIndex,
        start: clamped.start,
        end: clamped.end,
      }
    }

    if (drag.kind === 'move') {
      const newStart = Math.max(0, time - drag.grabOffset)
      const clamped = clampToSameTrack(
        stateRef.current.regions,
        drag.trackIndex,
        drag.regionId,
        newStart,
        newStart + drag.width,
      )
      // 幅維持を優先（ぶつかった端で止める）
      const start = clamped.start
      return {
        id: drag.regionId,
        trackIndex: drag.trackIndex,
        start,
        end: start + drag.width,
      }
    }

    // resize
    let rawStart: number
    let rawEnd: number
    if (drag.edge === 'start') {
      rawStart = Math.min(time, drag.fixedTime)
      rawEnd = drag.fixedTime
    } else {
      rawStart = drag.fixedTime
      rawEnd = Math.max(time, drag.fixedTime)
    }
    const clamped = clampToSameTrack(
      stateRef.current.regions,
      drag.trackIndex,
      drag.regionId,
      rawStart,
      rawEnd,
    )
    return {
      id: drag.regionId,
      trackIndex: drag.trackIndex,
      start: clamped.start,
      end: clamped.end,
    }
  }

  const onWindowMouseMove = (event: MouseEvent) => {
    const drag = dragRef.current
    if (!drag) {
      return
    }
    event.preventDefault()

    // 作成・移動は移動量しきい値を超えるまで何もしない（クリック判定のため）
    if (
      (drag.kind === 'create' || drag.kind === 'move') &&
      !drag.moved &&
      Math.abs(event.clientX - drag.startX) >= REGION_DRAG_THRESHOLD_PX
    ) {
      drag.moved = true
    }
    if ((drag.kind === 'create' || drag.kind === 'move') && !drag.moved) {
      return
    }

    setDraftRegion(computeDraft(drag, event.clientX))
  }

  const onWindowMouseUp = (event: MouseEvent) => {
    const drag = dragRef.current
    stopWindowDrag()
    setDraftRegion(null)
    if (!drag) {
      return
    }

    if (drag.kind === 'create' && !drag.moved) {
      // クリック扱い → シーク
      controls.setCurrentTime(pixelToTime(event.clientX))
      return
    }
    if (drag.kind === 'move' && !drag.moved) {
      // 動かさずクリック → 選択のみ
      selectRegion(drag.regionId)
      return
    }

    // drag 情報から最終リージョンを再計算（State には依存しない）
    const draft = computeDraft(drag, event.clientX)
    if (draft.end - draft.start < REGION_MIN_DURATION) {
      return
    }

    const committed: Region =
      drag.kind === 'create' ? { ...draft, id: makeRegionId() } : draft
    commitActive(committed)
    if (drag.kind === 'create') {
      selectRegion(committed.id)
    }
  }

  const stopWindowDrag = () => {
    window.removeEventListener('mousemove', onWindowMouseMove)
    window.removeEventListener('mouseup', onWindowMouseUp)
    dragRef.current = null
  }

  const startWindowDrag = (drag: RegionDragState) => {
    dragRef.current = drag
    window.addEventListener('mousemove', onWindowMouseMove)
    window.addEventListener('mouseup', onWindowMouseUp)
  }

  // リージョン矩形上の mousedown（移動 or リサイズ or 選択）
  const onRegionMouseDown = (event: React.MouseEvent, region: Region) => {
    event.stopPropagation()
    event.preventDefault()
    const rect = event.currentTarget.getBoundingClientRect()
    const offsetX = event.clientX - rect.left
    const time = pixelToTime(event.clientX)

    if (offsetX <= REGION_RESIZE_HANDLE_PX) {
      startWindowDrag({
        kind: 'resize',
        regionId: region.id,
        trackIndex: region.trackIndex,
        edge: 'start',
        fixedTime: region.end,
        startX: event.clientX,
      })
      selectRegion(region.id)
      return
    }
    if (offsetX >= rect.width - REGION_RESIZE_HANDLE_PX) {
      startWindowDrag({
        kind: 'resize',
        regionId: region.id,
        trackIndex: region.trackIndex,
        edge: 'end',
        fixedTime: region.start,
        startX: event.clientX,
      })
      selectRegion(region.id)
      return
    }
    startWindowDrag({
      kind: 'move',
      regionId: region.id,
      trackIndex: region.trackIndex,
      grabOffset: time - region.start,
      width: region.end - region.start,
      startX: event.clientX,
      moved: false,
    })
  }

  // 空き領域（上部80%）の mousedown（作成 or クリックシーク）
  const onEmptyMouseDown = (event: React.MouseEvent, trackIndex: number) => {
    event.preventDefault()
    startWindowDrag({
      kind: 'create',
      trackIndex,
      anchorTime: pixelToTime(event.clientX),
      startX: event.clientX,
      startY: event.clientY,
      moved: false,
    })
  }

  // 表示するリージョン（draft があれば該当を差し替え）
  const displayRegions: Region[] = (() => {
    if (!draftRegion) return regions
    if (draftRegion.id === '__draft__') return [...regions, draftRegion]
    return regions.map((r) => (r.id === draftRegion.id ? draftRegion : r))
  })()

  if (!scrollEl) return null

  const tracksWidth = data.duration > 0
    ? Math.ceil((data.duration * data.sampleRate) / data.samplesPerPixel)
    : scrollEl.scrollWidth

  const overlay = (
    <div className="region-layer" style={{ left: 0, width: tracksWidth, top: 0, bottom: 0 }}>
      {/* トラックごとの上部80%キャプチャ帯（作成・クリックシーク用） */}
      {layouts.map((layout) => (
        <div
          key={`capture-${layout.trackIndex}`}
          className="region-capture"
          style={{
            top: layout.top,
            height: layout.height * REGION_HEIGHT_RATIO,
          }}
          onMouseDown={(event) => onEmptyMouseDown(event, layout.trackIndex)}
        />
      ))}

      {/* リージョン矩形 */}
      {displayRegions.map((region) => {
        const layout = layouts.find((l) => l.trackIndex === region.trackIndex)
        if (!layout) return null
        const left = timeToPixel(region.start)
        const width = Math.max(1, timeToPixel(region.end) - left)
        const isSelected = region.id === selectedRegionId
        const isDraft = region.id === '__draft__'
        return (
          <div
            key={region.id}
            className={
              'region-box' +
              (isSelected ? ' selected' : '') +
              (isDraft ? ' draft' : '')
            }
            style={{
              left,
              width,
              top: layout.top,
              height: layout.height * REGION_HEIGHT_RATIO,
            }}
            onMouseDown={
              isDraft ? undefined : (event) => onRegionMouseDown(event, region)
            }
            onMouseMove={
              isDraft
                ? undefined
                : (event) => {
                    const rect = event.currentTarget.getBoundingClientRect()
                    const offsetX = event.clientX - rect.left
                    const isHandle =
                      offsetX <= REGION_RESIZE_HANDLE_PX ||
                      offsetX >= rect.width - REGION_RESIZE_HANDLE_PX
                    event.currentTarget.style.cursor = isHandle ? 'col-resize' : 'grab'
                  }
            }
          />
        )
      })}
    </div>
  )

  return createPortal(overlay, scrollEl)
}

function RegionPlaybackGate() {
  const playback = usePlaybackAnimation()
  const data = usePlaylistData()
  const { regions } = useRegions()
  const { soloedTrackIndex } = useSoloState()

  // ゲートが mute を一元管理する。各トラックの実際の mute は単一の muteGain ノードで、
  // ユーザーの M ボタンとゲートが同じ muteGain を共有するため、別管理にすると競合する。
  // そこで effectiveMute = ユーザー mute(trackStates[i].muted) || リージョン無し を毎フレーム
  // 合成し、engine.setTrackMute を trackId 指定で直接適用する（state を介さず各トラック独立）。
  const regionsRef = useRef(regions)
  const soloedTrackIndexRef = useRef(soloedTrackIndex)
  useEffect(() => {
    soloedTrackIndexRef.current = soloedTrackIndex
  }, [soloedTrackIndex])
  useEffect(() => {
    regionsRef.current = regions
  }, [regions])
  const tracksRef = useRef(data.tracks)
  useEffect(() => {
    tracksRef.current = data.tracks
  }, [data.tracks])
  const trackStatesRef = useRef(data.trackStates)
  useLayoutEffect(() => {
    trackStatesRef.current = data.trackStates
  }, [data.trackStates])

  // 直前にゲートで適用した mute 状態（trackId 単位）
  const lastGateRef = useRef<Map<string, boolean>>(new Map())
  // 停止中（rAF が回らない）でも再適用できるよう applyGate を ref で保持
  const applyGateRef = useRef<() => void>(() => {})

  useEffect(() => {
    const engine = data.playoutRef.current
    if (!engine) {
      return
    }
    lastGateRef.current = new Map()

    const applyGate = () => {
      const eng = data.playoutRef.current
      if (!eng) {
        return
      }
      const t = playback.currentTimeRef.current ?? 0
      const regs = regionsRef.current
      const states = trackStatesRef.current
      const soloIdx = soloedTrackIndexRef.current
      tracksRef.current.forEach((track, i) => {
        const hasRegion = regs.some(
          (r) => r.trackIndex === i && t >= r.start && t < r.end,
        )
        const userMuted = states[i]?.muted ?? false
        // ソロ中トラック: リージョンゲートをバイパス（普通のソロ再生）
        // 他トラックがソロ中: 消音
        // ソロなし: リージョンゲート通常動作
        const effectiveMute = userMuted || (soloIdx !== null ? soloIdx !== i : !hasRegion)
        if (lastGateRef.current.get(track.id) !== effectiveMute) {
          eng.setTrackMute(track.id, effectiveMute)
          lastGateRef.current.set(track.id, effectiveMute)
        }
      })
    }
    applyGateRef.current = applyGate

    playback.registerFrameCallback('region-gate', applyGate)
    // 再生していなくても現在位置で一度適用
    applyGate()

    return () => {
      playback.unregisterFrameCallback('region-gate')
      // ユーザー本来の mute 設定（trackStates[i].muted）へ復元
      const eng = data.playoutRef.current
      if (eng) {
        const states = trackStatesRef.current
        tracksRef.current.forEach((track, i) => {
          eng.setTrackMute(track.id, states[i]?.muted ?? false)
        })
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 停止中の Mボタン操作・リージョン変更でもゲートを即再適用（rAF を待たない）。
  // trackStates 変化直後に controls.setTrackMute が engine.setTrackMute を呼んで
  // muteGain を変えてしまうため、useLayoutEffect で DOM 更新前に上書きする。
  useLayoutEffect(() => {
    applyGateRef.current()
  }, [data.trackStates, regions, soloedTrackIndex])

  return null
}

// SPACE=停止して先頭へ戻る、ENTER=再生/一時停止
function PlaybackKeyboard() {
  const controls = usePlaylistControls()
  const playback = usePlaybackAnimation()
  const state = usePlaylistState()
  const data = usePlaylistData()

  const controlsRef = useRef(controls)
  useEffect(() => {
    controlsRef.current = controls
  }, [controls])

  const dataRef = useRef(data)
  useEffect(() => {
    dataRef.current = data
  }, [data])

  const selectionRangeRef = useRef(getSelectionRange(state.selectionStart, state.selectionEnd))
  useEffect(() => {
    selectionRangeRef.current = getSelectionRange(state.selectionStart, state.selectionEnd)
  }, [state.selectionStart, state.selectionEnd])

  const loopRangeRef = useRef(getLoopRange(state.loopStart, state.loopEnd))
  useEffect(() => {
    loopRangeRef.current = getLoopRange(state.loopStart, state.loopEnd)
  }, [state.loopStart, state.loopEnd])

  const isLoopEnabledRef = useRef(state.isLoopEnabled)
  useEffect(() => {
    isLoopEnabledRef.current = state.isLoopEnabled
  }, [state.isLoopEnabled])

  const isPlayingRef = useRef(playback.isPlaying)
  useEffect(() => {
    isPlayingRef.current = playback.isPlaying
  }, [playback.isPlaying])

  useEffect(() => {
    const playFromCurrentState = () => {
      const currentTime = playback.currentTimeRef.current ?? 0
      const startTime = getLoopAwarePlayStart(
        currentTime,
        loopRangeRef.current,
        isLoopEnabledRef.current,
      )
      if (startTime !== currentTime) {
        controlsRef.current.setCurrentTime(startTime)
      }
      void controlsRef.current.play(startTime)
    }

    const isEditingTarget = (target: EventTarget | null) =>
      target instanceof HTMLElement &&
      Boolean(target.closest('input, textarea, select, [contenteditable="true"]'))

    const deleteSelectedClip = () => {
      const focused = document.querySelector<HTMLElement>('.clip-focus-visible')
      const clipId = focused?.dataset.clipId
      if (!clipId) return false

      const d = dataRef.current
      for (const track of d.tracks) {
        if (track.clips.some((c) => c.id === clipId)) {
          const newClips = track.clips.filter((c) => c.id !== clipId)
          d.playoutRef.current?.updateTrack(track.id, { ...track, clips: newClips })
          focused.classList.remove('clip-focus-visible')
          return true
        }
      }
      return false
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.repeat || isEditingTarget(event.target)) {
        return
      }
      if (event.key === 'Delete' || event.key === 'Backspace') {
        if (deleteSelectedClip()) {
          event.preventDefault()
        }
        return
      }
      if (event.key === ' ') {
        event.preventDefault()
        if (isPlayingRef.current) {
          controlsRef.current.stop()
        } else {
          playFromCurrentState()
        }
        return
      }
      if (event.key.toLowerCase() === 'l') {
        const selectionRange = selectionRangeRef.current
        const loopRange = loopRangeRef.current
        if (selectionRange) {
          event.preventDefault()
          controlsRef.current.setLoopRegion(selectionRange.start, selectionRange.end)
          if (!isLoopEnabledRef.current) {
            controlsRef.current.setLoopEnabled(true)
          }
          controlsRef.current.setSelection(0, 0)
          return
        }
        if (loopRange) {
          event.preventDefault()
          controlsRef.current.setLoopEnabled(!isLoopEnabledRef.current)
        }
        return
      }
      if (event.key === 'Enter') {
        event.preventDefault()
        if (isPlayingRef.current) {
          controlsRef.current.pause()
        } else {
          playFromCurrentState()
        }
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [playback.currentTimeRef])

  return null
}

function RegionKeyboard() {
  const playback = usePlaybackAnimation()
  const { regions, setRegions, selectedRegionId, setSelectedRegionId } = useRegions()

  const stateRef = useRef({ regions, selectedRegionId })
  useEffect(() => {
    stateRef.current = { regions, selectedRegionId }
  }, [regions, selectedRegionId])

  useEffect(() => {
    const isEditingTarget = (target: EventTarget | null) =>
      target instanceof HTMLElement &&
      Boolean(target.closest('input, textarea, select, [contenteditable="true"]'))

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.repeat || isEditingTarget(event.target)) {
        return
      }
      const { selectedRegionId: selId, regions: regs } = stateRef.current

      if (event.key === 'Delete' || event.key === 'Backspace') {
        if (selId) {
          event.preventDefault()
          setRegions((current) => current.filter((r) => r.id !== selId))
          setSelectedRegionId(null)
        }
        return
      }

      if (event.key.toLowerCase() === 'r') {
        // 再生位置でリージョン分割
        const t = playback.currentTimeRef.current ?? 0
        const target = regs.find((r) => t > r.start && t < r.end)
        if (!target) {
          return
        }
        event.preventDefault()
        const left: Region = { ...target, end: t }
        const right: Region = {
          ...target,
          id: makeRegionId(),
          start: t,
        }
        setRegions((current) => {
          const others = current.filter((r) => r.id !== target.id)
          const next: Region[] = [...others]
          if (left.end - left.start >= REGION_MIN_DURATION) {
            next.push(left)
          }
          if (right.end - right.start >= REGION_MIN_DURATION) {
            next.push(right)
          }
          return next
        })
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return null
}

function TrackControls({
  trackIndex,
  trackHeightMode,
  canMoveUp,
  canMoveDown,
  onMoveTrack,
}: {
  trackIndex: number
  trackHeightMode: TrackHeightMode
  canMoveUp: boolean
  canMoveDown: boolean
  onMoveTrack: (trackIndex: number, direction: -1 | 1) => void
}) {
  const controls = usePlaylistControls()
  const data = usePlaylistData()
  const { soloedTrackIndex, setSoloedTrackIndex } = useSoloState()
  const track = data.tracks[trackIndex]
  const trackState = data.trackStates[trackIndex]

  if (!trackState || !track) {
    return null
  }

  return (
    <div className={trackHeightMode === 'small' ? 'track-controls compact' : 'track-controls'}>
      <div className="track-header-row">
        <strong>{trackState.name || track.name}</strong>
        <div className="track-order-buttons">
          <button
            type="button"
            className="track-order-button"
            disabled={!canMoveUp}
            title="トラックを上へ移動"
            aria-label={`${trackState.name || track.name} を上へ移動`}
            onClick={() => onMoveTrack(trackIndex, -1)}
          >
            <ChevronUp size={13} />
          </button>
          <button
            type="button"
            className="track-order-button"
            disabled={!canMoveDown}
            title="トラックを下へ移動"
            aria-label={`${trackState.name || track.name} を下へ移動`}
            onClick={() => onMoveTrack(trackIndex, 1)}
          >
            <ChevronDown size={13} />
          </button>
        </div>
      </div>
      <button
        type="button"
        className={soloedTrackIndex === trackIndex ? 'track-toggle active' : 'track-toggle'}
        onClick={() => {
          const next = soloedTrackIndex !== trackIndex ? trackIndex : null
          setSoloedTrackIndex(next)
          const engine = data.playoutRef.current
          data.tracks.forEach((t, i) => {
            const s = next === i
            if (engine) engine.setTrackSolo(t.id, s)
          })
        }}
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
