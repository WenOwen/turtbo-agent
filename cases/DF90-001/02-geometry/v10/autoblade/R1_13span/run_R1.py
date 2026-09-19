import os
par_path = r"D:/Project/Research/turtbo-agent/cases/DF90-001/02-geometry/v10/autoblade/R1_13span/R1.par"
abp_path = r"D:/Project/Research/turtbo-agent/cases/DF90-001/02-geometry/v10/autoblade/R1_13span/R1.abp"
geom_path = r"D:/Project/Research/turtbo-agent/cases/DF90-001/02-geometry/v10/autoblade/R1_13span/R1.geomTurbo"
print("SCRIPT_BEGIN v8_build")
if not ab_project_create(abp_path):
    raise RuntimeError("ab_project_create failed: %s" % abp_path)
if not ab_project_load_model(par_path):
    raise RuntimeError("ab_project_load_model failed: %s" % par_path)
if not ab_model_update_all():
    raise RuntimeError("ab_model_update_all failed")
if not ab_project_save_as(abp_path):
    raise RuntimeError("ab_project_save_as failed")
export_result = ab_model_export_geomturbo(geom_path)
print("GEOMTURBO_EXPORT_RESULT %s" % export_result)
if (not export_result) and (not os.path.exists(geom_path)):
    raise RuntimeError("ab_model_export_geomturbo failed: %s" % geom_path)
print("SCRIPT_RETURN_VALUE 1")
