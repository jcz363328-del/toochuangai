export interface MarketOverviewRow {
  period: string;
  salesVolume: number | null;
  salesAmount: number;
  monthOverMonthGrowth: number | null;
  averageOrderValue: number | null;
  partial?: boolean;
}

export const MARKET_OVERVIEW_ROWS: MarketOverviewRow[] = [
  { period: "2024-06", salesVolume: 1988522, salesAmount: 21267254.8, monthOverMonthGrowth: null, averageOrderValue: 10.70 },
  { period: "2024-07", salesVolume: 2113748, salesAmount: 22248911.48, monthOverMonthGrowth: 0.0441, averageOrderValue: 10.53 },
  { period: "2024-08", salesVolume: 2025428, salesAmount: 21688713.71, monthOverMonthGrowth: -0.0258, averageOrderValue: 10.71 },
  { period: "2024-09", salesVolume: 1988204, salesAmount: 20978230.95, monthOverMonthGrowth: -0.0339, averageOrderValue: 10.55 },
  { period: "2024-10", salesVolume: 2183816, salesAmount: 22432418.52, monthOverMonthGrowth: 0.0648, averageOrderValue: 10.27 },
  { period: "2024-11", salesVolume: 2073457, salesAmount: 21196968.57, monthOverMonthGrowth: -0.0583, averageOrderValue: 10.22 },
  { period: "2024-12", salesVolume: 2155258, salesAmount: 23026079.02, monthOverMonthGrowth: 0.0794, averageOrderValue: 10.68 },
  { period: "2025-01", salesVolume: 1969250, salesAmount: 21323939.56, monthOverMonthGrowth: -0.0798, averageOrderValue: 10.83 },
  { period: "2025-02", salesVolume: 1972403, salesAmount: 21190490.63, monthOverMonthGrowth: -0.0063, averageOrderValue: 10.74 },
  { period: "2025-03", salesVolume: 2203072, salesAmount: 23788659.29, monthOverMonthGrowth: 0.1092, averageOrderValue: 10.80 },
  { period: "2025-04", salesVolume: 2166843, salesAmount: 23343774.67, monthOverMonthGrowth: -0.0191, averageOrderValue: 10.77 },
  { period: "2025-05", salesVolume: 2374100, salesAmount: 25856752.65, monthOverMonthGrowth: 0.0972, averageOrderValue: 10.89 },
  { period: "2025-06", salesVolume: 2296569, salesAmount: 25371604.24, monthOverMonthGrowth: -0.0191, averageOrderValue: 11.05 },
  { period: "2025-07", salesVolume: 2573065, salesAmount: 27847550.12, monthOverMonthGrowth: 0.0889, averageOrderValue: 10.82 },
  { period: "2025-08", salesVolume: 2605161, salesAmount: 28944180.74, monthOverMonthGrowth: 0.0379, averageOrderValue: 11.11 },
  { period: "2025-09", salesVolume: 2532485, salesAmount: 27832788.92, monthOverMonthGrowth: -0.0399, averageOrderValue: 10.99 },
  { period: "2025-10", salesVolume: 2843210, salesAmount: 30620055.22, monthOverMonthGrowth: 0.0910, averageOrderValue: 10.77 },
  { period: "2025-11", salesVolume: 2791232, salesAmount: 29225013.38, monthOverMonthGrowth: -0.0477, averageOrderValue: 10.47 },
  { period: "2025-12", salesVolume: 2890085, salesAmount: 32669412.31, monthOverMonthGrowth: 0.1054, averageOrderValue: 11.30 },
  { period: "2026-01", salesVolume: 2656647, salesAmount: 30118638.17, monthOverMonthGrowth: -0.0847, averageOrderValue: 11.34 },
  { period: "2026-02", salesVolume: 2645751, salesAmount: 30017004.61, monthOverMonthGrowth: -0.0034, averageOrderValue: 11.35 },
  { period: "2026-03", salesVolume: 2978390, salesAmount: 33702187.41, monthOverMonthGrowth: 0.1093, averageOrderValue: 11.32 },
  { period: "2026-04", salesVolume: 2924993, salesAmount: 33235785.22, monthOverMonthGrowth: -0.0140, averageOrderValue: 11.36 },
  { period: "2026-05", salesVolume: 2991184, salesAmount: 34057647.77, monthOverMonthGrowth: 0.0241, averageOrderValue: 11.39 },
  { period: "2026-06", salesVolume: 3044091, salesAmount: 33859538.05, monthOverMonthGrowth: -0.0059, averageOrderValue: 11.12 },
  { period: "2026-07", salesVolume: 2918223, salesAmount: 33002255.42, monthOverMonthGrowth: -0.0260, averageOrderValue: 11.31 },
  { period: "2026-08", salesVolume: 2975704, salesAmount: 33773954.08, monthOverMonthGrowth: 0.0228, averageOrderValue: 11.35 },
  { period: "2026-09", salesVolume: 2874723, salesAmount: 32766075.25, monthOverMonthGrowth: -0.0308, averageOrderValue: 11.40 },
];
