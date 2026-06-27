# -*- coding: utf-8 -*-
# 复用精细版逻辑，但清空家具/圆，输出"无家具空壳 45°轴测"——给外部工具贴材质、视角锁死
src = open("axon_v2.py", encoding="utf-8").read()
src = src.replace('axon_v2.svg', 'axon_empty.svg')
# 在家具循环前清空 furn/circ
src = src.replace('for x, y, w, h, fill in furn:',
                  'furn = []; circ = []\nfor x, y, w, h, fill in furn:')
exec(src)
