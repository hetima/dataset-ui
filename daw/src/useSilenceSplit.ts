import { useCallback } from 'react'
import { usePlaylistData } from '@waveform-playlist/browser'
import { buildVoicedClips, detectVoicedRegions } from './silenceSplit'

/**
 * フォーカス中の1クリップを -60dB 無音で複数クリップに分割する関数を返す。
 * engine.updateTrack 経由で適用するため Undo で1回で取り消せる。
 */
export function useSilenceSplit() {
  const data = usePlaylistData()

  return useCallback(() => {
    // フォーカス中クリップの clipId を DOM から取得（ClipHeader が data-clip-id を出す）。
    const focused = document.querySelector<HTMLElement>('.clip-focus-visible')
    const clipId = focused?.dataset.clipId
    if (!clipId) {
      window.alert('クリップを選択してください')
      return
    }

    // clipId から trackIndex / clip を逆引き。
    let trackIndex = -1
    let clipIndex = -1
    for (let t = 0; t < data.tracks.length; t += 1) {
      const ci = data.tracks[t].clips.findIndex((c) => c.id === clipId)
      if (ci !== -1) {
        trackIndex = t
        clipIndex = ci
        break
      }
    }
    if (trackIndex === -1) {
      window.alert('選択クリップが見つかりませんでした')
      return
    }

    const track = data.tracks[trackIndex]
    const clip = track.clips[clipIndex]
    if (!clip.audioBuffer) {
      window.alert('このクリップには音声データがありません')
      return
    }

    const regions = detectVoicedRegions(
      clip.audioBuffer,
      clip.offsetSamples,
      clip.durationSamples,
      clip.sampleRate,
    )
    if (regions.length === 0) {
      window.alert('有音区間が見つかりませんでした')
      return
    }
    // 分割結果が1個（＝丸ごと有音）なら変化しないので何もしない。
    if (regions.length === 1) {
      window.alert('無音区間が見つからず、分割の必要がありませんでした')
      return
    }

    const voicedClips = buildVoicedClips(clip, regions)
    // 対象クリップだけ複数クリップに置換、他はそのまま。
    const newClips = track.clips.flatMap((c) => (c.id === clipId ? voicedClips : [c]))

    const engine = data.playoutRef.current
    if (!engine) {
      window.alert('エンジンが準備できていません')
      return
    }
    // updateTrack は undo スナップショットを積み、該当トラックのみ再構築する。
    engine.updateTrack(track.id, { ...track, clips: newClips })
  }, [data])
}
