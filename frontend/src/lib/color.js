/**
 * Colour maths for the group colour picker.
 *
 * hslToRgb deliberately mirrors DMXInterface._hsl_to_rgb in
 * backend/dmx_interface.py, truncation included, because the backend is what
 * actually drives the fixtures: the RGB the picker shows must be the RGB the
 * lights receive. Both implementations are pinned to the same reference
 * fixture (tests/fixtures/hsl_reference.json), so a change to either without
 * the other fails the suites.
 */

/**
 * @param h hue 0-360
 * @param s saturation 0-100
 * @param l lightness 0-100
 * @returns { r, g, b } each 0-255
 */
export function hslToRgb(h, s, l) {
  s = s / 100
  l = l / 100

  if (s === 0) {
    const val = Math.trunc(l * 255)
    return { r: val, g: val, b: val }
  }

  const c = (1 - Math.abs(2 * l - 1)) * s
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1))
  const m = l - c / 2

  let r, g, b
  if (h < 60) { r = c; g = x; b = 0 }
  else if (h < 120) { r = x; g = c; b = 0 }
  else if (h < 180) { r = 0; g = c; b = x }
  else if (h < 240) { r = 0; g = x; b = c }
  else if (h < 300) { r = x; g = 0; b = c }
  else { r = c; g = 0; b = x }

  return {
    r: Math.trunc((r + m) * 255),
    g: Math.trunc((g + m) * 255),
    b: Math.trunc((b + m) * 255)
  }
}

/**
 * Inverse of hslToRgb, used to seed the picker from a fixture's current
 * channel values. There is no backend counterpart.
 *
 * @returns { h: 0-360, s: 0-100, l: 0-100 }
 */
export function rgbToHsl(r, g, b) {
  r /= 255
  g /= 255
  b /= 255

  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const l = (max + min) / 2

  if (max === min) {
    return { h: 0, s: 0, l: Math.round(l * 100) }
  }

  const d = max - min
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min)

  let h
  if (max === r) h = ((g - b) / d + (g < b ? 6 : 0))
  else if (max === g) h = (b - r) / d + 2
  else h = (r - g) / d + 4
  h /= 6

  return {
    h: Math.round(h * 360),
    s: Math.round(s * 100),
    l: Math.round(l * 100)
  }
}
