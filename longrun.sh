# This takes around 4 hours to create all the optimized PNG files,
# but once you have them, then save temp_folder/ somewhere, for example rename it to precalculated_pngs/
# and then you can use it for subsequent runs.

#time python3 duke3d_compact_grp.py --ultraminimalmenu --pngquant 69-71 --zopflipng --keep-temp /home/user/ESP32_NES/duke3d/DUKE3D_v1.3d_shareware.grp --output outputs/DUKE3D_v1.3d_shareware_pngquant_69-71_2
#mv temp_folder/ precalculated_pngs_pngquant_69-71_2

time python3 duke3d_compact_grp.py --ultraminimalmenu --pngquant 40-71 --zopflipng --keep-temp /home/user/ESP32_NES/duke3d/DUKE3D_v1.3d_shareware.grp --output outputs/DUKE3D_v1.3d_shareware_pngquant_40-71_2
mv temp_folder/ precalculated_pngs_pngquant_40-71_2
