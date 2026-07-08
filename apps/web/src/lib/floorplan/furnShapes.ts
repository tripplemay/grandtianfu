// 声明式俯视外形 (软装重构 Phase C-3 / 画家具外形 #3-2) —— 引擎 plan2d_shapes.py 的前端孪生
// 解释器。消费同一份 catalog.plan2d_spec (经 /api/catalog 下发), 把 (footprint + orient + spec)
// 翻译成绘制原语, 让编辑器画布与画廊平面图外形一致 (床头板/沙发扶手/盆/柜门线)。

export interface Plan2dPart {
  k: string; // edge | arms | inner | doors
  depth?: number;
  width?: number;
  inset?: number[];
  rx?: number;
  n?: number;
}

export interface ShapePrim {
  k: 'rect' | 'line';
  x?: number;
  y?: number;
  w?: number;
  h?: number;
  rx?: number;
  hollow?: boolean;
  x1?: number;
  y1?: number;
  x2?: number;
  y2?: number;
}

const ORIENTS = ['N', 'S', 'W', 'E'];
const clamp = (v: number, lo: number, hi: number) =>
  Math.max(lo, Math.min(hi, v));

function edgeRect(
  x: number,
  y: number,
  w: number,
  h: number,
  o: string,
  depth: number,
): ShapePrim {
  const d = clamp(depth, 0, 0.9);
  if (o === 'S') return { k: 'rect', x, y: y + h * (1 - d), w, h: h * d };
  if (o === 'W') return { k: 'rect', x, y, w: w * d, h };
  if (o === 'E') return { k: 'rect', x: x + w * (1 - d), y, w: w * d, h };
  return { k: 'rect', x, y, w, h: h * d }; // N
}

function armRects(
  x: number,
  y: number,
  w: number,
  h: number,
  o: string,
  depth: number,
  width: number,
): ShapePrim[] {
  const d = clamp(depth, 0, 1);
  const wd = clamp(width, 0, 0.45);
  if (o === 'N' || o === 'S') {
    const y0 = o === 'N' ? y : y + h * (1 - d);
    const hh = h * d;
    return [
      { k: 'rect', x, y: y0, w: w * wd, h: hh },
      { k: 'rect', x: x + w * (1 - wd), y: y0, w: w * wd, h: hh },
    ];
  }
  const x0 = o === 'W' ? x : x + w * (1 - d);
  const ww = w * d;
  return [
    { k: 'rect', x: x0, y, w: ww, h: h * wd },
    { k: 'rect', x: x0, y: y + h * (1 - wd), w: ww, h: h * wd },
  ];
}

// 内缩按 orient 旋转 (作者按 orient=N 书写; 与 plan2d_shapes._rotate_inset 逐行等价)。
function rotateInset(
  inset: number[],
  o: string,
): [number, number, number, number] {
  const [l = 0, t = 0, r = 0, b = 0] = inset;
  if (o === 'E') return [b, l, t, r];
  if (o === 'S') return [r, b, l, t];
  if (o === 'W') return [t, r, b, l];
  return [l, t, r, b];
}

function innerRect(
  x: number,
  y: number,
  w: number,
  h: number,
  o: string,
  inset: number[],
  rx: number,
): ShapePrim {
  const [l, t, r, b] = rotateInset(inset, o);
  return {
    k: 'rect',
    x: x + w * l,
    y: y + h * t,
    w: w * Math.max(0, 1 - l - r),
    h: h * Math.max(0, 1 - t - b),
    rx,
    hollow: true,
  };
}

function doorLines(
  x: number,
  y: number,
  w: number,
  h: number,
  o: string,
  n: number,
): ShapePrim[] {
  const cnt = Math.max(1, Math.round(n));
  const out: ShapePrim[] = [];
  if (o === 'N' || o === 'S') {
    for (let i = 1; i < cnt; i += 1) {
      const lx = x + (w * i) / cnt;
      out.push({ k: 'line', x1: lx, y1: y, x2: lx, y2: y + h });
    }
  } else {
    for (let i = 1; i < cnt; i += 1) {
      const ly = y + (h * i) / cnt;
      out.push({ k: 'line', x1: x, y1: ly, x2: x + w, y2: ly });
    }
  }
  return out;
}

export function detailPrims(
  x: number,
  y: number,
  w: number,
  h: number,
  orient: string | undefined,
  spec: Plan2dPart[],
): ShapePrim[] {
  const o = orient && ORIENTS.includes(orient) ? orient : 'N';
  const prims: ShapePrim[] = [];
  for (const part of spec || []) {
    if (part.k === 'edge') {
      prims.push(edgeRect(x, y, w, h, o, part.depth ?? 0.15));
    } else if (part.k === 'arms') {
      prims.push(
        ...armRects(x, y, w, h, o, part.depth ?? 0.8, part.width ?? 0.12),
      );
    } else if (part.k === 'inner') {
      prims.push(
        innerRect(
          x,
          y,
          w,
          h,
          o,
          part.inset ?? [0.1, 0.1, 0.1, 0.1],
          part.rx ?? 3,
        ),
      );
    } else if (part.k === 'doors') {
      prims.push(...doorLines(x, y, w, h, o, part.n ?? 2));
    }
  }
  return prims;
}
