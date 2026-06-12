# This takes around 4 hours for run to create all the optimized PNG files, so 12 hours total.
# But once you have them, then you can use it for subsequent runs, to make different variants.

time python3 duke3d_compact_grp.py --ultraminimalmenu --zopflipng --keep-temp input/DUKE3D_v1.3d_shareware.grp --output outputs/DUKE3D_v1.3d_shareware_pngquant_40-71_2.grp
mv temp_folder/ precalculated_pngs_shareware_1.3D

time python3 duke3d_compact_grp.py --ultraminimalmenu --pngquant 40-71 --zopflipng --keep-temp input/DUKE3D_v1.3d_shareware.grp --output outputs/DUKE3D_v1.3d_shareware_pngquant_40-71_2.grp
mv temp_folder/ precalculated_pngs_pngquant_40-71_2_iterations_500

time python3 duke3d_compact_grp.py --ultraminimalmenu --pngquant 10 --zopflipng --keep-temp input/DUKE3D_v1.3d_shareware.grp --output outputs/DUKE3D_v1.3d_shareware_pngquant_10.grp
mv temp_folder/ precalculated_pngs_pngquant_10_3 # the _3 is a misnomer, as the default is --posterize 2

# Full version test:
#time python3 duke3d_compact_grp.py --ultraminimalmenu --pngquant 40-71 --zopflipng --keep-temp /home/user/ESP32_NES/duke3d/DUKE3D_v1.3d_full.grp --output outputs/DUKE3D_v1.3d_full_pngquant_40-71_2.grp
#mv temp_folder/ precalculated_pngs_full_1.3D_pngquant_40-71_2
