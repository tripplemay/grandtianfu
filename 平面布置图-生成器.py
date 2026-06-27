# -*- coding: utf-8 -*-
# 在用户提供的精准底图上叠加家具层(同坐标系: group translate(150,250), 1px=10mm)
base = open("/Users/yixingzhou/project/grandtianfu/grand_tianfu_199m2_walkin_fixed.svg","r",encoding="utf-8-sig").read()

# ===== 实际装修:景观阳台已与客厅打通为同一区域 =====
base = base.replace('<rect class="room-outdoor" x="495" y="1255" width="720" height="155" />',
                    '<rect class="room-living" x="495" y="1255" width="720" height="155" />')
base = base.replace('<rect class="door-sliding" x="495" y="1250" width="720" height="5" />','')
base = base.replace('<text class="zh-label" x="855" y="1320">景观阳台</text><text class="en-label" x="855" y="1345">SOUTH BALCONY</text>',
                    '<text class="zh-label" x="855" y="1372">客厅·景观区</text><text class="en-label" x="855" y="1397">LIVING (EXTENDED)</text>')
# 次卧(一) 改为 书房
base = base.replace('<text class="zh-label" x="1365" y="360">次卧 (一)</text><text class="en-label" x="1365" y="385">GUESTROOM 1</text>',
                    '<text class="zh-label" x="1365" y="330">书房</text><text class="en-label" x="1365" y="355">STUDY</text>')

# ===== 修正东侧寝区进深(用户核定): 次卧二进深4.0m=y170-570; 公卫进深1.8m=y570-760 =====
# 书房变浅(y170-490), 前厅(内部过渡)上延(y490-760)以承接次卧二西墙门; 次卧二 y170-570; 公卫 y570-760
base = base.replace('<rect class="room-bedroom" x="1215" y="170" width="300" height="410" /> <rect class="room-bedroom" x="1515" y="170" width="300" height="490" /> <rect class="room-corridor" x="1215" y="580" width="300" height="180" />',
                    '<rect class="room-bedroom" x="1215" y="170" width="300" height="320" /> <rect class="room-bedroom" x="1515" y="170" width="300" height="400" /> <rect class="room-corridor" x="1215" y="490" width="300" height="270" />')
base = base.replace('<rect class="room-wet" x="1515" y="660" width="300" height="100" />',
                    '<rect class="room-wet" x="1515" y="570" width="300" height="190" />')
# x1515墙: 留出次卧二门(y490-570)与公卫门(y660-740)的门洞,不再实墙封堵
base = base.replace('<line class="wall-thick" x1="1515" y1="170" x2="1515" y2="580" />',
                    '<line class="wall-thick" x1="1515" y1="170" x2="1515" y2="490" /><line class="wall-thick" x1="1515" y1="570" x2="1515" y2="660" />')
# 删除箭头所指多余实墙: x1215 的 y490-580 段(内部过渡↔餐厅之间,本应开口连通寝区入口)
base = base.replace('<line class="wall-thick" x1="1215" y1="265" x2="1215" y2="580" />',
                    '<line class="wall-thick" x1="1215" y1="265" x2="1215" y2="490" />')
# 主卫门洞(x1515,y800-870)断开实墙
base = base.replace('<line class="wall-thick" x1="1515" y1="740" x2="1515" y2="1020" />',
                    '<line class="wall-thick" x1="1515" y1="740" x2="1515" y2="800" /><line class="wall-thick" x1="1515" y1="870" x2="1515" y2="1020" />')
base = base.replace('<line class="wall-thick" x1="1215" y1="580" x2="1430" y2="580" />',
                    '<line class="wall-thick" x1="1215" y1="490" x2="1430" y2="490" />')
base = base.replace('<line class="wall-thick" x1="1515" y1="660" x2="1815" y2="660" />',
                    '<line class="wall-thick" x1="1515" y1="570" x2="1815" y2="570" />')
base = base.replace('<path class="door-arc" d="M 1510 580 A 80 80 0 0 1 1430 660" /> <line class="door-leaf" x1="1430" y1="580" x2="1430" y2="660" />',
                    '<path class="door-arc" d="M 1510 490 A 80 80 0 0 1 1430 570" /> <line class="door-leaf" x1="1430" y1="490" x2="1430" y2="570" />')
base = base.replace('<path class="door-arc" d="M 1515 580 A 80 80 0 0 0 1435 660" /> <line class="door-leaf" x1="1515" y1="660" x2="1435" y2="660" />',
                    '<path class="door-arc" d="M 1515 500 A 75 75 0 0 0 1440 575" /> <line class="door-leaf" x1="1515" y1="500" x2="1440" y2="500" />')
base = base.replace('<text class="zh-label" x="1340" y="660">内部过渡</text><text class="en-label" x="1340" y="685">PRIVATE LOBBY</text>',
                    '<text class="zh-label" x="1340" y="625">内部过渡</text><text class="en-label" x="1340" y="650">PRIVATE LOBBY</text>')
base = base.replace('<text class="zh-label" x="1665" y="710">公卫</text><text class="en-label" x="1665" y="735">PUBLIC RESTROOM</text>',
                    '<text class="zh-label" x="1665" y="665">公卫</text><text class="en-label" x="1665" y="690">PUBLIC RESTROOM</text>')

# ===== 修正厨房/生活阳台进深(用户核定): 3.75m→2.25m, 南墙对齐书房南墙 y490 =====
base = base.replace('<rect class="room-wet" x="720" y="265" width="285" height="375" />',
                    '<rect class="room-wet" x="675" y="265" width="330" height="225" />')
base = base.replace('<rect class="room-outdoor" x="1005" y="265" width="210" height="375" />',
                    '<rect class="room-outdoor" x="1005" y="265" width="210" height="225" />')
base = base.replace('<line class="wall-thick" x1="720" y1="265" x2="720" y2="640" />',
                    '<line class="wall-thick" x1="675" y1="265" x2="675" y2="490" />')
# ===== 宽度修正(户型图): 厨房3300(x675-1005), 入户花园3100(x365-675); 仅内部分界x720→x675 =====
base = base.replace('M 180,250 L 365,250 L 365,0 L 720,0 L 720,265 L 1215,265',
                    'M 180,250 L 365,250 L 365,0 L 675,0 L 675,265 L 1215,265')
base = base.replace('<rect class="room-outdoor" x="365" y="0" width="355" height="250" />',
                    '<rect class="room-outdoor" x="365" y="0" width="310" height="250" />')
base = base.replace('<rect class="room-living" x="495" y="250" width="225" height="390" />',
                    '<rect class="room-living" x="495" y="250" width="180" height="390" />')
base = base.replace('<line class="dim-line" x1="365" y1="0" x2="720" y2="0" /><line class="dim-tick" x1="365" y1="-6" x2="365" y2="6" /><text class="dim-text" x="542" y="-15">3550</text>',
                    '<line class="dim-line" x1="365" y1="0" x2="675" y2="0" /><line class="dim-tick" x1="365" y1="-6" x2="365" y2="6" /><text class="dim-text" x="520" y="-15">3100</text>')
base = base.replace('<line class="dim-line" x1="720" y1="0" x2="1005" y2="0" /><line class="dim-tick" x1="720" y1="-6" x2="720" y2="6" /><text class="dim-text" x="862" y="-15">2850</text>',
                    '<line class="dim-line" x1="675" y1="0" x2="1005" y2="0" /><line class="dim-tick" x1="675" y1="-6" x2="675" y2="6" /><text class="dim-text" x="840" y="-15">3300</text>')

# ===== 主卧衣帽间扩大(户型图): 北墙北移一个公卫门宽(y760→y680); 西段北扩, 东侧留前室小过道 =====
base = base.replace('<rect class="room-bedroom" x="1215" y="760" width="300" height="260" />',
                    '<rect class="room-bedroom" x="1215" y="680" width="300" height="340" />')
base = base.replace('<line class="wall-thick" x1="1215" y1="760" x2="1430" y2="760" />',
                    '<line class="wall-thick" x1="1215" y1="680" x2="1435" y2="680" />')
base = base.replace('<line class="wall-thick" x1="1005" y1="265" x2="1005" y2="640" />',
                    '<line class="wall-thick" x1="1005" y1="265" x2="1005" y2="490" />')
base = base.replace('<rect class="room-living" x="495" y="640" width="720" height="615" />',
                    '<rect class="room-living" x="495" y="490" width="720" height="765" />')
base = base.replace('<rect class="door-sliding" x="745" y="637" width="85" height="5" /> <rect class="door-sliding" x="820" y="643" width="85" height="5" />',
                    '<rect class="door-sliding" x="745" y="487" width="85" height="5" /> <rect class="door-sliding" x="820" y="493" width="85" height="5" />')

STRUCT=[]   # 结构元素(墙/接缝)——无家具版也必须保留
WIN=[]      # 窗——无家具版也必须保留
F=[]        # 家具——无家具版排除
# 抹平客厅↔原阳台接缝(覆盖交界细线,呈现连通)
STRUCT.append('<rect x="500" y="1250" width="710" height="10" fill="#fcfdfd" stroke="none"/>')
# 厨房/阳台新南墙(y490): 留厨房移门口(x745-905)与阳台开口(x1120-1215)
STRUCT.append('<line x1="675" y1="490" x2="745" y2="490" stroke="#1a1a1a" stroke-width="7" stroke-linecap="round"/>')
STRUCT.append('<line x1="905" y1="490" x2="1120" y2="490" stroke="#1a1a1a" stroke-width="7" stroke-linecap="round"/>')
# 衣帽间扩大后: 增"南北向"墙(x1435,y680-760)与公卫门相对,围出前室小过道,衣帽间门(y760,x1435-1515)位置不变
STRUCT.append('<line x1="1435" y1="680" x2="1435" y2="760" stroke="#1a1a1a" stroke-width="7" stroke-linecap="round"/>')
# 补齐寝区西墙(x1215): 衣帽间+主卧西墙(y680-1255), 保留内部过渡入口开口(y490-680)
STRUCT.append('<line x1="1215" y1="680" x2="1215" y2="1255" stroke="#1a1a1a" stroke-width="7" stroke-linecap="round"/>')
def fr(x,y,w,h,fill="#ece0c8",stroke="#b9a274",rx=2):
    F.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>')
def bed(x,y,w,h):  # 床(暖驼)+床头板
    F.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4" fill="#e3c9a6" stroke="#b78f5e" stroke-width="1.4"/>')
def sofa(x,y,w,h): fr(x,y,w,h,fill="#d8c19c",stroke="#a9895c")
def soft(x,y,w,h): fr(x,y,w,h,fill="#cfe0d4",stroke="#7fa088")  # 椅/软座 绿
def wet(x,y,w,h):  fr(x,y,w,h,fill="#dde7ec",stroke="#8aa6b4")  # 洁具
def circ(cx,cy,r,fill="#cfe0d4",stroke="#7fa088"):
    F.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>')
def rug(x,y,w,h):
    F.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="#c9bb96" stroke-width="1" stroke-dasharray="6,4"/>')
def t(x,y,s,sz=12,c="#5a4a33"):
    F.append(f'<text x="{x}" y="{y}" font-family="Microsoft YaHei,PingFang SC,sans-serif" font-size="{sz}" fill="{c}" text-anchor="middle" dominant-baseline="middle">{s}</text>')

# ===== 入户花园 =====
circ(420,90,22,fill="#cfe0cf",stroke="#6b8a6b"); circ(470,70,16,fill="#cfe0cf",stroke="#6b8a6b"); t(540,180,"绿植景观",12,"#6b8a6b")
# ===== 玄关 =====
fr(190,258,150,38); t(265,277,"鞋柜",11)
fr(360,258,120,38); t(420,277,"装饰高柜+镜",8)
fr(190,560,150,40); t(265,580,"端景台/换鞋凳",9)
circ(430,560,22,fill="#cfe0cf",stroke="#6b8a6b")
# ===== 厨房 L型橱柜 (x675-1005, 进深收窄至y490) =====
fr(680,270,320,40); fr(680,270,40,215); t(845,450,"L型橱柜",10)
# ===== 生活阳台 (进深收窄至y490) =====
fr(1010,275,195,60); t(1107,420,"洗烘塔+收纳",9)

# ===== 餐厅区 =====
# 餐边柜→餐厅西侧墙边; 3.0×1.1m 长餐桌(E-W,8人), 距厨房墙留≥1.1m通道
fr(500,560,44,210); t(585,665,"餐边柜",9)
# 长餐桌 3.0×1.1m 8人, 东西向(长轴沿 x); 椅子分南北两排各4
fr(700,600,300,110); t(850,655,"长餐桌 3.0×1.1m (8人)",9)
for cx in (738,813,888,963):
    fr(cx-22,580,44,20,fill="#cfe0d4",stroke="#7fa088"); fr(cx-22,710,44,20,fill="#cfe0d4",stroke="#7fa088")
# ===== 客厅(含原阳台,连通) L沙发面东墙影视墙 + 茶几 + 南窗景观休闲角 =====
rug(700,985,360,320)
F.append('<line x1="1206" y1="1020" x2="1206" y2="1250" stroke="#7a3f2a" stroke-width="4"/>')
fr(1158,1040,44,200,fill="#cdb18f",stroke="#8a6a44"); t(1095,1140,"东墙胡桃木影视墙",9,"#7a3f2a")
sofa(720,1008,96,232); t(768,1124,"三人沙发",9)              # 主沙发(西,面东)
sofa(816,1190,210,80); t(925,1230,"转角贵妃",9)             # L转角贵妃(东向)
fr(900,1070,100,108,fill="#e7d9bb",stroke="#b9ad8a"); t(950,1124,"茶几",9)
# 南窗景观休闲角: 旋转椅×2(可转向南窗赏景) + 绿植
soft(610,1330,66,66); soft(700,1330,66,66); circ(782,1362,24,fill="#e7d9bb",stroke="#b9ad8a")
t(700,1306,"景观休闲角(旋转椅)",8,"#5a7a55")
circ(1010,1372,22,fill="#cfe0cf",stroke="#6b8a6b"); circ(1062,1360,15,fill="#cfe0cf",stroke="#6b8a6b")

# ===== 书房 STUDY (原次卧一, 1215-1515,170-580; 门在南墙SE) =====
fr(1248,185,205,66); t(1350,218,"书桌",9)                 # 书桌靠北窗(E-W)
fr(1479,185,34,285); t(1496,500,"书柜",8)                 # 整墙书柜(东墙)
fr(1220,275,86,200); t(1335,375,"沙发床(留宿)",8)         # 西墙双人沙发床(0.86m), 房深3.2m内
soft(1325,398,72,72); circ(1416,432,15,fill="#e7d9bb",stroke="#b9ad8a"); t(1361,486,"阅读椅",8,"#3a5a3a")
# ===== 次卧(二) GUESTROOM2 (1515-1815,170-660) =====
bed(1585,185,160,200); t(1665,290,"双人床",10)
fr(1545,185,38,46); fr(1747,185,38,46)            # 床头柜
fr(1600,524,210,42); t(1705,545,"衣柜",9)          # 衣柜→南墙(y570)东段,靠墙;避开SW西门开启半径
fr(1770,330,40,150,fill="#cfe0d4",stroke="#7fa088"); t(1700,470,"书桌/梳妆",9)
# ===== 内部过渡(前厅) (1215-1515,580-760) =====
fr(1225,590,120,36); t(1340,712,"前厅过渡",10,"#7a6c54")
# ===== 公卫 (1515-1815,570-760; 进深1.8m) =====
wet(1530,582,120,38); t(1590,601,"台盆",8)         # 台盆靠北墙
wet(1745,628,55,90); t(1772,673,"马桶",8)          # 马桶
t(1620,720,"公卫 1.8m进深",7,"#8aa6b4")
# ===== 主卧衣帽间 CLOAKROOM (扩大: 西段y680-1020, 全宽y760-1020) =====
fr(1220,685,205,38)                                # 北墙(西段y680)衣柜
fr(1220,685,40,330)                                # 西墙衣柜
fr(1475,885,38,130)                                # 东墙衣柜(下移至主卫门下方,不挡主卫门y800-870)
fr(1300,852,120,130,fill="#e7d9bb",stroke="#b9ad8a"); t(1360,917,"中岛",9)
# ===== 主卫 MASTER BATH (1515-1815,760-1020) =====
# 门在西墙 y800-870; 洁具均避开门洞与开启半径
wet(1560,768,165,40); t(1642,788,"双台盆",9)        # 北墙(东移,让出门口)
wet(1530,905,58,95); t(1559,952,"厕",8)             # SW角,门下方
fr(1620,872,95,128,fill="#dde7ec",stroke="#8aa6b4"); t(1667,936,"淋浴",8,"#4a6470")  # 中南,门开启半径外
wet(1735,850,72,160); t(1771,930,"浴缸",8)          # 东墙窗
# ===== 主卧睡眠区 MASTER BEDROOM (1215-1815,1020-1410) =====
bed(1608,1120,202,182); t(1709,1211,"双人床1.8m",9)   # 头靠东墙(x1810≈墙1815)
fr(1766,1078,42,40); fr(1766,1302,42,40)              # 床头柜(东墙两侧)
# 弧形贵妃榻(西)
F.append('<path d="M 1320 1135 A 92 92 0 0 1 1320 1319" fill="#cdd9e0" stroke="#7a93a0" stroke-width="1.4"/>')
t(1372,1227,"弧形贵妃榻",9,"#4a6470")
rug(1575,1100,245,225)
# ===== 次卧套房 GUEST SUITE (180-495,1020-1410) =====
bed(255,1095,180,200); t(345,1195,"1.8床/沙发床",9)
fr(190,1030,42,250,fill="#cdb18f"); t(211,1155,"衣柜",8)
soft(300,1320,60,60); circ(400,1350,22,fill="#e7d9bb",stroke="#b9ad8a")
# ===== 次卫 BATH (0-180,1020-1410) =====
wet(20,1100,60,40); wet(20,1200,55,80); t(90,1320,"淋浴/洁具",9)

# ===== 补充窗户(依据官方户型图 7aa30e0b95c37aadd4d234f2b5d5a571.jpeg, 用户核定) =====
# 类型 data-wtype: full=落地窗 / normal=普通窗 / high=卫浴高窗 (供轴测图按类型出窗高)
# 客厅·景观区 南窗 标记为落地窗
base = base.replace('<rect class="window" x="495" y="1405" width="720" height="10" />',
                    '<rect class="window" data-wtype="full" x="495" y="1405" width="720" height="10" />')
# 南侧所有窗改落地窗(用户定): 次卧套房南 + 主卧南 (客厅景观南上面已设full; 次卫南见下方win_new)
base = base.replace('<rect class="window" x="180" y="1405" width="315" height="10" />',
                    '<rect class="window" data-wtype="full" x="180" y="1405" width="315" height="10" />')
base = base.replace('<rect class="window" x="1215" y="1405" width="600" height="10" />',
                    '<rect class="window" data-wtype="full" x="1215" y="1405" width="600" height="10" />')
def win_new(x, y, w, h, wtype="normal"):
    WIN.append(f'<rect class="window" data-wtype="{wtype}" x="{x}" y="{y}" width="{w}" height="{h}"/>')
win_new(705, 260, 260, 10, "normal")   # 厨房 北窗
win_new(1035, 260, 150, 10, "full")    # 生活阳台 北窗(落地)
win_new(1805, 820, 10, 190, "high")    # 主卫 东窗(高窗)
win_new(1805, 600, 10, 130, "high")    # 公卫 东窗(高窗)
win_new(20, 1405, 140, 10, "full")     # 次卫 南窗(落地, 南侧统一落地)
win_new(395, -5, 250, 10, "full")      # 入户花园 北窗(落地)
win_new(360, 30, 10, 190, "full")      # 入户花园 西窗(落地)
win_new(195, 245, 160, 10, "full")     # 玄关 北窗(落地)
# 注：次卧二 东墙经核定为实墙，无窗

import re
# 玄关西北侧入户门标识(原图未标，导致玄关被误布置)
base = base.replace('<g id="room_labels">',
                    '<g id="room_labels">\n      <text class="zh-label" x="255" y="335">入户门</text><text class="en-label" x="255" y="358">ENTRANCE</text>')
struct_svg = "\n".join(STRUCT)
window_svg = '<g id="window-layer">\n' + "\n".join(WIN) + '\n</g>\n'
furniture = '<g id="furniture-layer">\n' + struct_svg + '\n' + "\n".join(F) + '\n</g>\n'

# ---- 含家具版(平面布置图)现已统一由 轴测图POC/户型-D户型.py 按 FURNITURE 表生成 ----
# 本生成器只负责"几何源"(无家具版,见下)，避免与家具表产生两个真源。
# (旧的 furniture 层保留在上方仅作参考，不再写入 平面布置图.svg)
_ = furniture  # 旧家具层不再输出

# ---- 无家具干净版(结构墙+窗+房间+房名;去家具/标题/尺寸标注)——给外部工具做45°效果图底图 ----
nf = base.replace('<g id="room_labels">',
                  '<g id="struct-layer">\n' + struct_svg + '\n</g>\n' + window_svg + '    <g id="room_labels">')
nf = re.sub(r'<g transform="translate\(120, 90\)">.*?</g>', '', nf, flags=re.S)       # 去标题
for tr in ('0, -50', '0, 1560', '-60, 0', '1880, 0'):                                  # 去四组尺寸标注
    nf = re.sub(r'<g transform="translate\(' + re.escape(tr) + r'\)">.*?</g>', '', nf, flags=re.S)
open("/Users/yixingzhou/project/grandtianfu/平面布置图-无家具.svg","w",encoding="utf-8-sig").write(nf)
print("furniture-free plan written")
