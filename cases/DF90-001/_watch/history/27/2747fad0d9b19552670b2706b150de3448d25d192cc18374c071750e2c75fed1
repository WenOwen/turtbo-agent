# -*- coding: utf-8 -*-
# 由 optimize_existing_mesh.py 生成；不替换几何。
a5_open_project('D:/Project/Research/Ducted-Fan/run/90kg-duct-fan-v8/mesh/mesh-v1/mesh-v1.trb')
if a5_get_row_number() < 1:
    raise RuntimeError('source row count is smaller than configured row index')
row(1).blade(1).set_b2b_default_topology_grid_point_number_streamwise_blade_upper_side(97)
a5_save_project('D:/Project/Research/Ducted-Fan/run/90kg-duct-fan-v8/mesh/mesh-v2/mesh-v2.trb')
a5_generate_3d([row(1)])
a5_save_mesh('D:/Project/Research/Ducted-Fan/run/90kg-duct-fan-v8/mesh/mesh-v2/mesh-v2.igg')
a5_export_CGNS_project('D:/Project/Research/Ducted-Fan/run/90kg-duct-fan-v8/mesh/mesh-v2/mesh-v2.cgns')
a5_save_project('D:/Project/Research/Ducted-Fan/run/90kg-duct-fan-v8/mesh/mesh-v2/mesh-v2.trb')
print('AUTOGRID_JOB_DONE')
