# 电路器件连接关系

- 来源：`2026_EDA_case1 / OPA / schematic`（服务器 PyAether 读取）
- 端口（9 个）：IREF VCM VOUTP SUB VOUTN VINN VDDA GNDA VINP
- 器件总数：**41**（MOS 29 / R 6 / C 6）
- 端口占位实例：9 个（PIN0, PIN3, PIN2, PIN8, PIN7, PIN1, PIN6, PIN5, PIN4，ipin/iopin，0 端子，已从器件统计中剔除）

| 器件 | 类型 | master | 端子→网 | 尺寸参数 |
|---|---|---|---|---|
| PM0 | MOS | p_mos_a | D:net6, G:net6, S:VDDA, B:VDDA | l=4u, w=4u, m=2 |
| PM1 | MOS | p_mos_a | D:net37, G:net6, S:VDDA, B:VDDA | l=4u, w=32u, m=10 |
| PM2 | MOS | p_mos_a | D:net0, G:vcmfb, S:VDDA, B:VDDA | l=2u, w=160u, m=10 |
| PM3 | MOS | p_mos_a | D:net8, G:vcmfb, S:VDDA, B:VDDA | l=2u, w=160u, m=10 |
| PM4 | MOS | p_mos_a | D:net13, G:net6, S:VDDA, B:VDDA | l=4u, w=16u, m=10 |
| PM5 | MOS | p_mos_a | D:net5, G:net5, S:VDDA, B:VDDA | l=4u, w=4u, m=10 |
| PM6 | MOS | p_mos_a | D:vcmfb, G:net5, S:VDDA, B:VDDA | l=4u, w=4u, m=10 |
| NM5 | MOS | n_mos_a | D:net8, G:IREF, S:net44, B:SUB | l=2u, w=16u, m=2 |
| PM8 | MOS | p_mos_a | D:net3, G:VCM, S:net13, B:VDDA | l=2u, w=48u, m=10 |
| NM0 | MOS | n_mos_a | D:IREF, G:IREF, S:net53, B:SUB | l=2u, w=2u, m=2 |
| NM1 | MOS | n_mos_a | D:net6, G:IREF, S:net32, B:SUB | l=2u, w=2u, m=2 |
| NM2 | MOS | n_mos_a | D:net53, G:net53, S:GNDA, B:SUB | l=2u, w=2u, m=2 |
| NM3 | MOS | n_mos_a | D:net32, G:net53, S:GNDA, B:SUB | l=2u, w=2u, m=2 |
| PM9 | MOS | p_mos_a | D:net4, G:VINP, S:net37, B:VDDA | l=2u, w=8u, m=4 |
| PM10 | MOS | p_mos_a | D:net44, G:VINN, S:net37, B:VDDA | l=2u, w=8u, m=4 |
| NM4 | MOS | n_mos_a | D:net0, G:IREF, S:net4, B:SUB | l=2u, w=16u, m=2 |
| NM6 | MOS | n_mos_a | D:net4, G:net53, S:GNDA, B:SUB | l=2u, w=16u, m=4 |
| NM7 | MOS | n_mos_a | D:net44, G:net53, S:GNDA, B:SUB | l=2u, w=16u, m=4 |
| PM7 | MOS | p_mos_a | D:VOUTP, G:net0, S:VDDA, B:VDDA | l=2u, w=16u, m=10 |
| PM11 | MOS | p_mos_a | D:VOUTN, G:net8, S:VDDA, B:VDDA | l=2u, w=16u, m=10 |
| NM8 | MOS | n_mos_a | D:VOUTP, G:net53, S:GNDA, B:GNDA | l=2u, w=16u, m=10 |
| NM9 | MOS | n_mos_a | D:VOUTN, G:net53, S:GNDA, B:GNDA | l=2u, w=16u, m=10 |
| PM12 | MOS | p_mos_a | D:net52, G:outaverage, S:net13, B:VDDA | l=2u, w=48u, m=10 |
| NM10 | MOS | n_mos_a | D:net5, G:IREF, S:net3, B:SUB | l=2u, w=2u, m=10 |
| NM11 | MOS | n_mos_a | D:vcmfb, G:IREF, S:net52, B:SUB | l=2u, w=2u, m=10 |
| NM12 | MOS | n_mos_a | D:net3, G:net53, S:GNDA, B:SUB | l=2u, w=8u, m=10 |
| NM13 | MOS | n_mos_a | D:net52, G:net53, S:GNDA, B:SUB | l=2u, w=8u, m=10 |
| C2 | C | cap_mim | 1:VOUTP, 2:outaverage | m=1, l=30u, fw=20u, c=17.76f |
| R0 | R | res_p_poly | 1:outaverage, 2:VOUTP | m=1, segL=74u, segW=420n, segments=10, l=740u, w=420n, r=525.376K |
| R5 | R | res_n_poly | 1:net11, 2:net11 | m=1, segL=25u, segW=10u, segments=1, l=25u, w=10u, r=839.583 |
| C3 | C | cap_mim | 1:outaverage, 2:VOUTN | m=1, l=30u, fw=20u, c=17.76f |
| C4 | C | cap_mim | 1:net11, 2:net11 | m=1, l=20u, fw=10u, c=5.92f |
| R2 | R | res_p_poly | 1:net7, 2:net8 | m=1, segL=25u, segW=10u, segments=1, l=25u, w=10u, r=641.305 |
| C0 | C | cap_mim | 1:VOUTN, 2:net7 | m=2, l=30u, fw=30u, c=26.64f |
| C11 | C | cap_mim | 1:VOUTP, 2:net17 | m=2, l=30u, fw=30u, c=26.64f |
| R1 | R | res_p_poly | 1:net17, 2:net0 | m=1, segL=25u, segW=10u, segments=1, l=25u, w=10u, r=641.305 |
| R3 | R | res_p_poly | 1:VOUTN, 2:outaverage | m=1, segL=74u, segW=420n, segments=10, l=740u, w=420n, r=525.376K |
| NM14 | MOS | n_mos_a | D:VOUTP, G:IREF, S:VOUTP, B:SUB | l=2u, w=2u, m=10 |
| NM15 | MOS | n_mos_a | D:VOUTN, G:IREF, S:VOUTN, B:SUB | l=2u, w=2u, m=10 |
| R6 | R | res_n_poly | 1:net12, 2:net12 | m=1, segL=25u, segW=10u, segments=1, l=25u, w=10u, r=839.583 |
| C5 | C | cap_mim | 1:net12, 2:net12 | m=1, l=20u, fw=10u, c=5.92f |
