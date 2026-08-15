import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { hslToRgb, rgbToHsl } from '../src/lib/color.js'

// vitest runs with the frontend directory as cwd
const reference = JSON.parse(
  readFileSync(resolve(process.cwd(), '../tests/fixtures/hsl_reference.json'), 'utf8'))

describe('hslToRgb', () => {
  it.each([
    ['white', 0, 0, 100, [255, 255, 255]],
    ['black', 0, 0, 0, [0, 0, 0]],
    ['red', 0, 100, 50, [255, 0, 0]],
    ['green', 120, 100, 50, [0, 255, 0]],
    ['blue', 240, 100, 50, [0, 0, 255]],
    ['yellow', 60, 100, 50, [255, 255, 0]],
    ['cyan', 180, 100, 50, [0, 255, 255]],
    ['magenta', 300, 100, 50, [255, 0, 255]]
  ])('%s', (_name, h, s, l, [r, g, b]) => {
    expect(hslToRgb(h, s, l)).toEqual({ r, g, b })
  })

  it('is achromatic when saturation is zero, whatever the hue', () => {
    for (const h of [0, 90, 200, 359]) {
      const { r, g, b } = hslToRgb(h, 0, 50)
      expect(r).toBe(g)
      expect(g).toBe(b)
    }
  })

  it('keeps every channel inside the DMX range', () => {
    for (let h = 0; h <= 360; h += 7) {
      for (const s of [0, 33, 66, 100]) {
        for (const l of [0, 20, 50, 80, 100]) {
          const { r, g, b } = hslToRgb(h, s, l)
          for (const v of [r, g, b]) {
            expect(v).toBeGreaterThanOrEqual(0)
            expect(v).toBeLessThanOrEqual(255)
            expect(Number.isInteger(v)).toBe(true)
          }
        }
      }
    }
  })

  it('treats hue 360 as hue 0', () => {
    expect(hslToRgb(360, 100, 50)).toEqual(hslToRgb(0, 100, 50))
  })
})

// ---------------------------------------------------------------------------
// Cross-language contract
//
// The backend drives the fixtures, so the RGB shown in the picker has to be
// the RGB the lights get. tests/fixtures/hsl_reference.json is generated from
// DMXInterface._hsl_to_rgb and asserted by both suites.
// ---------------------------------------------------------------------------
describe('parity with the backend', () => {
  it('has a reference fixture with samples in it', () => {
    expect(reference.samples.length).toBeGreaterThan(500)
  })

  it('matches the backend on every reference sample', () => {
    const mismatches = reference.samples.filter((s) => {
      const got = hslToRgb(s.h, s.s, s.l)
      return got.r !== s.r || got.g !== s.g || got.b !== s.b
    })

    expect(mismatches).toEqual([])
  })

  it('truncates like the backend rather than rounding', () => {
    // 50% grey is 127.5; the backend truncates, so the picker must too or it
    // would advertise a value one higher than the fixture receives
    expect(hslToRgb(0, 0, 50)).toEqual({ r: 127, g: 127, b: 127 })
  })
})

describe('rgbToHsl', () => {
  it.each([
    ['white', 255, 255, 255, { h: 0, s: 0, l: 100 }],
    ['black', 0, 0, 0, { h: 0, s: 0, l: 0 }],
    ['red', 255, 0, 0, { h: 0, s: 100, l: 50 }],
    ['green', 0, 255, 0, { h: 120, s: 100, l: 50 }],
    ['blue', 0, 0, 255, { h: 240, s: 100, l: 50 }]
  ])('%s', (_name, r, g, b, expected) => {
    expect(rgbToHsl(r, g, b)).toEqual(expected)
  })

  it('reports zero saturation for any grey', () => {
    for (const v of [0, 64, 128, 200, 255]) {
      expect(rgbToHsl(v, v, v).s).toBe(0)
    }
  })

  it('round trips the saturated primaries and secondaries', () => {
    for (const h of [0, 60, 120, 180, 240, 300]) {
      const { r, g, b } = hslToRgb(h, 100, 50)
      const back = rgbToHsl(r, g, b)
      expect(back.h).toBe(h === 360 ? 0 : h)
      expect(back.s).toBe(100)
      expect(Math.abs(back.l - 50)).toBeLessThanOrEqual(1)
    }
  })

  it('stays within its documented ranges', () => {
    for (let r = 0; r <= 255; r += 51) {
      for (let g = 0; g <= 255; g += 51) {
        for (let b = 0; b <= 255; b += 51) {
          const { h, s, l } = rgbToHsl(r, g, b)
          expect(h).toBeGreaterThanOrEqual(0)
          expect(h).toBeLessThanOrEqual(360)
          expect(s).toBeGreaterThanOrEqual(0)
          expect(s).toBeLessThanOrEqual(100)
          expect(l).toBeGreaterThanOrEqual(0)
          expect(l).toBeLessThanOrEqual(100)
        }
      }
    }
  })
})
