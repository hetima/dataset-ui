import type { AudioClip } from '@waveform-playlist/browser'

// 無音判定の閾値（dB）。これ未満を無音フレームとみなす。
export const SILENCE_THRESH_DB = -60
// 有音クリップの最低長（秒）。これ未満になる有音は前後の無音を取り込んで伸ばす。
export const MIN_VOICED_SEC = 1.0
// これ未満の連続無音は「削る無音区間」とみなさない（短い無音は有音に含める）。
export const MIN_SILENCE_SEC = 0.3
// RMS 計算の窓サイズ（サンプル）。
const RMS_FRAME = 1024
// RMS 計算のホップサイズ（サンプル）。
const RMS_HOP = 256

export type Region = { start: number; end: number }

/**
 * クリップの有音範囲 [offsetSamples, offsetSamples+durationSamples) を走査し、
 * -60dB 無音で区切った有音区間（audioBuffer 内サンプル位置）を返す。
 * 短い無音は無視し、有音が最低 MIN_VOICED_SEC になるよう前後の無音を取り込む。
 */
export function detectVoicedRegions(
  audioBuffer: AudioBuffer,
  offsetSamples: number,
  durationSamples: number,
  sampleRate: number,
): Region[] {
  const scanStart = Math.max(0, Math.floor(offsetSamples))
  const scanEnd = Math.min(audioBuffer.length, Math.floor(offsetSamples + durationSamples))
  if (scanEnd - scanStart < RMS_FRAME) {
    return []
  }

  const channelCount = audioBuffer.numberOfChannels
  const channels: Float32Array[] = []
  for (let ch = 0; ch < channelCount; ch += 1) {
    channels.push(audioBuffer.getChannelData(ch))
  }

  // フレームごとに無音/有音を判定したマスク（true=無音）。
  const frameStarts: number[] = []
  const isSilent: boolean[] = []
  for (let pos = scanStart; pos + RMS_FRAME <= scanEnd; pos += RMS_HOP) {
    let sumSquares = 0
    for (let i = 0; i < RMS_FRAME; i += 1) {
      let mixed = 0
      for (let ch = 0; ch < channelCount; ch += 1) {
        mixed += channels[ch][pos + i] ?? 0
      }
      const sample = mixed / channelCount
      sumSquares += sample * sample
    }
    const rms = Math.sqrt(sumSquares / RMS_FRAME)
    const db = rms === 0 ? -Infinity : 20 * Math.log10(rms)
    frameStarts.push(pos)
    isSilent.push(db < SILENCE_THRESH_DB)
  }

  if (frameStarts.length === 0) {
    return []
  }

  // 連続無音区間を抽出し、MIN_SILENCE_SEC 以上のものだけ「削る無音」とする。
  const minSilenceSamples = Math.round(MIN_SILENCE_SEC * sampleRate)
  const silenceRegions: Region[] = []
  let runStart = -1
  for (let f = 0; f < isSilent.length; f += 1) {
    if (isSilent[f] && runStart === -1) {
      runStart = frameStarts[f]
    } else if (!isSilent[f] && runStart !== -1) {
      const runEnd = frameStarts[f]
      if (runEnd - runStart >= minSilenceSamples) {
        silenceRegions.push({ start: runStart, end: runEnd })
      }
      runStart = -1
    }
  }
  // 末尾まで無音が続いた場合
  if (runStart !== -1) {
    const runEnd = scanEnd
    if (runEnd - runStart >= minSilenceSamples) {
      silenceRegions.push({ start: runStart, end: runEnd })
    }
  }

  // 削る無音区間の隙間 = 有音区間。
  const voiced: Region[] = []
  let cursor = scanStart
  for (const sil of silenceRegions) {
    if (sil.start > cursor) {
      voiced.push({ start: cursor, end: sil.start })
    }
    cursor = sil.end
  }
  if (cursor < scanEnd) {
    voiced.push({ start: cursor, end: scanEnd })
  }

  // 有音が MIN_VOICED_SEC 未満なら、前後の無音を取り込んで伸ばす。
  // 伸長は走査範囲 [scanStart, scanEnd) と隣接有音区間でクランプする。
  const minVoicedSamples = Math.round(MIN_VOICED_SEC * sampleRate)
  for (let i = 0; i < voiced.length; i += 1) {
    const region = voiced[i]
    let shortfall = minVoicedSamples - (region.end - region.start)
    if (shortfall <= 0) {
      continue
    }
    // 前方に伸ばせる限界（前の有音区間の終端、無ければ走査開始）
    const prevLimit = i > 0 ? voiced[i - 1].end : scanStart
    // 後方に伸ばせる限界（次の有音区間の開始、無ければ走査終了）
    const nextLimit = i < voiced.length - 1 ? voiced[i + 1].start : scanEnd

    // 後方優先で伸ばす
    const expandEnd = Math.min(shortfall, nextLimit - region.end)
    region.end += expandEnd
    shortfall -= expandEnd
    if (shortfall > 0) {
      const expandStart = Math.min(shortfall, region.start - prevLimit)
      region.start -= expandStart
    }
  }

  return voiced
}

/**
 * 有音区間（audioBuffer 内サンプル位置）から新しい AudioClip 群を生成する。
 * audioBuffer / waveformData は共有し、タイムライン位置（startSample）は維持する。
 */
export function buildVoicedClips(clip: AudioClip, regions: Region[]): AudioClip[] {
  return regions.map((region, index) => {
    const offsetSamples = region.start
    const durationSamples = region.end - region.start
    // 元クリップの offset からの差分をタイムライン位置に反映（位置維持）。
    const startSample = clip.startSample + (region.start - clip.offsetSamples)
    const name = clip.name ? `${clip.name} (${index + 1})` : undefined

    return {
      ...clip,
      id:
        typeof crypto !== 'undefined' && crypto.randomUUID
          ? crypto.randomUUID()
          : `clip-${Date.now()}-${index}-${Math.random().toString(36).slice(2, 8)}`,
      startSample,
      durationSamples,
      offsetSamples,
      name,
      // 分割後は startTick を再導出させるため落とす（エンジンが startSample から補完する）。
      startTick: undefined,
      // フェードは元クリップ全体のものなので分割後は引き継がない。
      fadeIn: undefined,
      fadeOut: undefined,
    }
  })
}
