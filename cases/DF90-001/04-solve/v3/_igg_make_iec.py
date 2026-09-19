igg_script_version(2.1)
import os
open_igg_project(r"D:\\Project\\Research\\turtbo-agent\\cases\\DF90-001\\03-mesh\\v4\\mesh-v4.igg")
print("OPENED, blocks =", num_of_blocks())
save_project(r"D:\\Project\\Research\\turtbo-agent\\cases\\DF90-001\\04-solve\\v3\\mesh-v4.iec")
print("IGG_IEC_DONE")