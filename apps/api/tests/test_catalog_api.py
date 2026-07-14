# -*- coding: utf-8 -*-
"""/api/catalog 端点 (P2 前后端同源): 出参形状 + 与引擎目录一致 + 真实尺寸。"""
import pytest
from fastapi.testclient import TestClient

import main
from floorplan_core import catalog


@pytest.fixture
def client():
    return TestClient(main.app)


def test_catalog_shape_and_rev(client):
    r = client.get("/api/catalog")
    assert r.status_code == 200
    body = r.json()
    assert body["rev"] == catalog.CATALOG_REV
    assert isinstance(body["types"], list) and body["types"]


def test_catalog_covers_every_engine_type(client):
    """端点必须逐条暴露引擎目录 (单一真源: 前端不再硬编码类型)。"""
    body = client.get("/api/catalog").json()
    served = {e["t"] for e in body["types"]}
    assert served == set(catalog.CATALOG)


def test_catalog_carries_realistic_sizes(client):
    """真实默认尺寸随目录下发 (拖入尺寸真实化的数据源)。"""
    by_t = {e["t"]: e for e in client.get("/api/catalog").json()["types"]}
    assert by_t["bed"]["w"] == 180 and by_t["bed"]["h"] == 200  # 1800x2000mm
    assert by_t["plant"]["shape"] == "round" and by_t["plant"]["r"] == 20
    # 每条矩形件必带 w/h, 圆形件必带 r; 均带 zh/category + rooms 列表 (rug 可为空 = AI 不选)。
    for e in by_t.values():
        assert e["zh"] and e["category"] and isinstance(e["rooms"], list)
        if e["shape"] == "round":
            assert "r" in e
        else:
            assert "w" in e and "h" in e


def test_catalog_flags_match_engine(client):
    """tall/directional 标志与引擎派生集合一致 (前端可据此提示/约束)。"""
    by_t = {e["t"]: e for e in client.get("/api/catalog").json()["types"]}
    tall = {t for t, e in by_t.items() if e.get("tall")}
    directional = {t for t, e in by_t.items() if e.get("directional")}
    assert tall == set(catalog.HEIGHT_CONSTRAINED_TYPES)
    assert directional == set(catalog.DIRECTIONAL_TYPES)


def test_catalog_swap_group_covers_every_type(client):
    """换件分组 (Phase C): 每类必属一个 swap_group, 且分组类型全在目录内 (换件约束真源)。"""
    by_t = {e["t"]: e for e in client.get("/api/catalog").json()["types"]}
    # 端点每类都带 swap_group
    assert all(e.get("swap_group") for e in by_t.values()), [
        t for t, e in by_t.items() if not e.get("swap_group")
    ]
    # 分组内类型都真实存在, 且并集 = 全目录 (无遗漏/无幽灵类型)
    grouped = {t for types in catalog.SWAP_GROUPS.values() for t in types}
    assert grouped == set(catalog.CATALOG)
    # 单一归属: 每类只属一组
    assert sum(len(v) for v in catalog.SWAP_GROUPS.values()) == len(catalog.CATALOG)


def test_catalog_serves_decor_types(client):
    """decor-b1: 独立配饰件 wall_art/curtain 随目录下发 (前端家具库自动并入装饰组)。"""
    by_t = {e["t"]: e for e in client.get("/api/catalog").json()["types"]}
    for t in ("wall_art", "curtain"):
        assert t in by_t and by_t[t]["category"] == "decor"
        assert by_t[t]["directional"] is True


def test_catalog_serves_attach_registry(client):
    """decor-b1 F005: 附着配饰注册表下发 (前端单一真源, 约束「配饰」编辑分节)。"""
    body = client.get("/api/catalog").json()
    attach = body["attach"]
    assert set(attach) == set(catalog.DECOR_ATTACH)
    # 每类带 zh + hosts 白名单 (与引擎 DECOR_ATTACH.hosts 键一致); mount_z 不下发
    for t, s in attach.items():
        assert s["zh"] and isinstance(s["hosts"], list)
        assert set(s["hosts"]) == set(catalog.DECOR_ATTACH[t]["hosts"])
        assert "mount_z" not in s
    # 圆形宿主不在任何 hosts (与引擎一致)
    all_hosts = {h for s in attach.values() for h in s["hosts"]}
    assert not (all_hosts & set(catalog.ROUND_TYPES))
