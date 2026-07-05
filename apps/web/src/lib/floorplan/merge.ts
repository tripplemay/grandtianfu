// 并房 (CP5v2 贴合并房升级): 纯函数域逻辑 —— 整组并入目标房 + prev_space 快照 +
// 孤儿 space 清理 + 合并边界开洞检测。UI 状态 (点选模式) 类型也定义在此。

import type { Geometry, Opening, Room } from './types';
import { roomById, roomsInGroup, SNAP } from './geometry';
import { nextId } from './ids';

// 贴合并房点选目标状态: source 待并房, candidates 画布高亮候选 (点击即并入)。
export interface MergePick {
  source: string;
  candidates: string[];
}

export interface MergeResult {
  g: Geometry;
  groupId: string; // 合并组 id
  groupIds: string[]; // 合并后组内全部房 id (供选中整组)
  moved: string[]; // 实际被并入 (space/merge 被改写) 的房 id
}

// 房间显示名: label.zh 优先, 次选其 space 标签 (避免 toast 直接暴露内部 id), 退回 id。
export function roomDisplayName(g: Geometry, room: Room | null): string {
  if (!room) return '?';
  return room.label?.zh || g.spaces?.[room.space]?.label || room.id;
}

// 面积最大房 id (平局最小 id) —— 与引擎「代表房」规则一致; 打通无显式目标时用。
export function largestRoomId(g: Geometry, ids: string[]): string | null {
  let best: Room | null = null;
  for (const id of ids) {
    const r = roomById(g, id);
    if (!r) continue;
    if (!best) {
      best = r;
      continue;
    }
    const a = r.rect[2] * r.rect[3];
    const ba = best.rect[2] * best.rect[3];
    if (a > ba || (a === ba && r.id < best.id)) best = r;
  }
  return best?.id ?? null;
}

// 清孤儿 space: 未被任何房间 space / 开洞 between 引用的条目移出字典。
// 仅在并房/分隔等空间归属变更后调用, 不做加载期全局静默清理。
export function pruneOrphanSpaces(g: Geometry): Geometry {
  const used = new Set<string>(g.rooms.map((r) => r.space));
  for (const op of g.openings ?? []) {
    for (const s of op.between ?? []) used.add(s);
  }
  const keys = Object.keys(g.spaces ?? {});
  if (keys.every((k) => used.has(k))) return g;
  const spaces: Geometry['spaces'] = {};
  for (const k of keys) {
    if (used.has(k)) spaces[k] = g.spaces[k];
  }
  return { ...g, spaces };
}

// 洞的宿主墙段是否落在 a×b 两房的共享边上 (轴向 at 贴边 + span 与重叠区间相交)。
function _onSharedEdge(op: Opening, a: Room, b: Room): boolean {
  const { axis, at, span } = op.wall ?? {};
  if (!axis || at == null || !span) return false;
  const [ax, ay, aw, ah] = a.rect;
  const [bx, by, bw, bh] = b.rect;
  if (axis === 'v') {
    const edge =
      Math.abs(ax + aw - bx) < SNAP ? ax + aw : Math.abs(bx + bw - ax) < SNAP ? bx + bw : null;
    if (edge == null || Math.abs(at - edge) >= SNAP) return false;
    const lo = Math.max(ay, by);
    const hi = Math.min(ay + ah, by + bh);
    return Math.min(span[1], hi) - Math.max(span[0], lo) > 1e-6;
  }
  const edge =
    Math.abs(ay + ah - by) < SNAP ? ay + ah : Math.abs(by + bh - ay) < SNAP ? by + bh : null;
  if (edge == null || Math.abs(at - edge) >= SNAP) return false;
  const lo = Math.max(ax, bx);
  const hi = Math.min(ax + aw, bx + bw);
  return Math.min(span[1], hi) - Math.max(span[0], lo) > 1e-6;
}

// 合并边界上的开洞: 宿主墙段落在「被并房 × 目标组」任一共享边上。并房后该段墙
// 因同 space 消隐, cut 洞会悬空触发引擎 D12 ERROR (校验拒存) —— 供并房 toast 提醒。
export function seamOpenings(
  g: Geometry,
  movedIds: string[],
  targetIds: string[],
): Opening[] {
  const movers = movedIds
    .map((id) => roomById(g, id))
    .filter((r): r is Room => r != null);
  const targets = targetIds
    .filter((id) => !movedIds.includes(id))
    .map((id) => roomById(g, id))
    .filter((r): r is Room => r != null);
  return (g.openings ?? []).filter((op) =>
    movers.some((a) => targets.some((b) => _onSharedEdge(op, a, b))),
  );
}

// 并房核心: sources 各自整组并入 target 所在组 —— space 归目标房 (保留目标名称/
// 类别, 并把目标房当前 label 刷新到 space 标签, 供组标签显示), 被并房记 prev_space
// 快照 (含原 space id, 供「分隔」还原且保持开洞 between 引用一致), 最后清孤儿
// space (被开洞 between 引用的原 space 保留)。无有效被并房 (不存在/已同组) 返回 null。
export function mergeIntoTarget(
  g: Geometry,
  sourceIds: string[],
  targetId: string,
): MergeResult | null {
  const target = roomById(g, targetId);
  if (!target) return null;
  const targetGroup = roomsInGroup(g, target);
  const inTarget = new Set(targetGroup.map((r) => r.id));
  const movers: Room[] = [];
  const moverIds = new Set<string>();
  for (const sid of sourceIds) {
    const src = roomById(g, sid);
    if (!src || sid === targetId) continue;
    for (const m of roomsInGroup(g, src)) {
      if (inTarget.has(m.id) || moverIds.has(m.id)) continue;
      moverIds.add(m.id);
      movers.push(m);
    }
  }
  if (!movers.length) return null;
  const groupId = target.merge || nextId('m');
  const rooms = g.rooms.map((r) => {
    if (moverIds.has(r.id)) {
      const next: Room = { ...r, space: target.space, merge: groupId };
      if (r.space !== target.space && !r.prev_space) {
        const sp = g.spaces?.[r.space];
        if (sp) {
          next.prev_space = {
            id: r.space,
            label: sp.label,
            category: sp.category,
            ...(sp.style ? { style: sp.style } : {}),
          };
        }
      }
      return next;
    }
    if (inTarget.has(r.id) && r.merge !== groupId) {
      return { ...r, merge: groupId };
    }
    return r;
  });
  // 组标签一致性: 组名显示走 space 标签, 并房时刷新为目标房当前 label。
  const tSpace = g.spaces?.[target.space];
  const tLabel = target.label?.zh;
  const spaces =
    tSpace && tLabel && tSpace.label !== tLabel
      ? { ...g.spaces, [target.space]: { ...tSpace, label: tLabel } }
      : g.spaces;
  const next = pruneOrphanSpaces({ ...g, rooms, spaces });
  return {
    g: next,
    groupId,
    groupIds: [...inTarget, ...moverIds],
    moved: [...moverIds],
  };
}
