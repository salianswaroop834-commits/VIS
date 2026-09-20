# Nexisure Canonical Dataset: 15 Users & 38 Mapped Vehicles

This document catalogs the 15 synthetic Indian users and their 38 associated vehicles seeded into the Nexisure platform.

> [!NOTE]
> **Authentication Credential**: All seeded demo customer users can authenticate locally using password `DemoCustomer@2026` or via OTP verification.
> **Identity & Vahan Lookup**: The PAN numbers and Vehicle registration numbers below are integrated into both the database and the RapidAPI simulation providers (`RapidApiPANProvider` and `RapidApiVehicleProvider`), matching registered mobile numbers for seamless 2FA KYC testing.

---

## 1. Master Mapping Table (15 Users & 38 Vehicles)

| # | Customer Name | Email | Phone Number | PAN Number | State / City | Mapped Vehicles Count | Vehicle Registration Numbers |
| :-: | :--- | :--- | :--- | :--- | :--- | :-: | :--- |
| **1** | **Aarav Patel** | `aarav.patel@nexisure.test` | `+919820112233` | `BNZPA1001A` | Maharashtra / Mumbai | **3** | `MH12AB1234`, `MH02CD5678`, `MH14EF9012` |
| **2** | **Priya Sharma** | `priya.sharma@nexisure.test` | `+919811223344` | `BKLPS2002B` | Delhi / New Delhi | **3** | `DL01AB2345`, `DL03CD6789`, `DL08EF0123` |
| **3** | **Rohan Iyer** | `rohan.iyer@nexisure.test` | `+919845334455` | `CAXPI3003C` | Karnataka / Bengaluru | **3** | `KA01AB3456`, `KA03CD7890`, `KA05EF1234` |
| **4** | **Ananya Sundaram** | `ananya.sundaram@nexisure.test` | `+919840445566` | `DEXPS4004D` | Tamil Nadu / Chennai | **3** | `TN01AB4567`, `TN07CD8901`, `TN09EF2345` |
| **5** | **Vikram Rathore** | `vikram.rathore@nexisure.test` | `+919829556677` | `EFGPR5005E` | Rajasthan / Jaipur | **3** | `RJ14AB0123`, `RJ45CD4567`, `DL10GH4567` |
| **6** | **Rajeshwari Kulkarni** | `rajeshwari.kulkarni@nexisure.test` | `+919822667788` | `FKLPK6006F` | Maharashtra / Thane | **3** | `MH04GH3456`, `MH47JK7890`, `KA51GH5678` |
| **7** | **Amitav Banerjee** | `amitav.banerjee@nexisure.test` | `+919830778899` | `GHMPB7007G` | West Bengal / Kolkata | **3** | `WB02AB9012`, `WB20CD3456`, `TN22GH6789` |
| **8** | **Sneha Deshmukh** | `sneha.deshmukh@nexisure.test` | `+919823889900` | `HJNPD8008H` | Maharashtra / Pune | **3** | `MH12KL1122`, `MH01MN3344`, `GJ01AB5678` |
| **9** | **Chirag Mehta** | `chirag.mehta@nexisure.test` | `+919879990011` | `JKOPM9009J` | Gujarat / Vadodara | **2** | `GJ06CD9012`, `GJ27EF3456` |
| **10** | **Neha Verma** | `neha.verma@nexisure.test` | `+919839001122` | `KLPPV1010K` | Uttar Pradesh / Lucknow | **2** | `UP32AB6789`, `UP16CD0123` |
| **11** | **Harpreet Singh** | `harpreet.singh@nexisure.test` | `+919814112233` | `LMNPS2020L` | Punjab / Mohali | **2** | `PB65AB2345`, `PB10CD6789` |
| **12** | **Deepa Nambiar** | `deepa.nambiar@nexisure.test` | `+919847223344` | `MNOPN3030M` | Kerala / Trivandrum | **2** | `KL01AB1234`, `KL07CD5678` |
| **13** | **Arjun Reddy** | `arjun.reddy@nexisure.test` | `+919849334455` | `NOPPR4040N` | Telangana / Hyderabad | **2** | `TS07AB7890`, `TS09CD1234` |
| **14** | **Pooja Choudhary** | `pooja.choudhary@nexisure.test` | `+919812445566` | `OPQPC5050P` | Haryana / Gurugram | **2** | `HR26AB8901`, `HR51CD2345` |
| **15** | **Alok Tiwari** | `alok.tiwari@nexisure.test` | `+919826556677` | `PQRPT6060Q` | Madhya Pradesh / Indore | **2** | `MP09AB3456`, `UP14EF4567` |

---

## 2. Complete Vehicle Registry Specifications (All 38 Vehicles)

| Reg Plate | Make & Model | Variant | Type | Fuel | Year | Insured Value (IDV) | Owner Name | Engine No | Chassis / VIN | RTO City |
| :--- | :--- | :--- | :--- | :--- | :---: | :---: | :--- | :--- | :--- | :--- |
| `MH12AB1234` | Hyundai Creta | SX (O) 1.5 Turbo DCT | SUV | Petrol | 2023 | ₹16,50,000 | Aarav Patel | `ENGMH121234981` | `VINMH12CRETA001A` | Pune RTO |
| `MH02CD5678` | Maruti Suzuki Swift | ZXi Plus AMT | Hatchback | Petrol | 2022 | ₹7,80,000 | Aarav Patel | `ENGMH025678120` | `VINMH02SWIFT002B` | Mumbai West RTO |
| `MH14EF9012` | Royal Enfield Classic 350 | Chrome Red Dual ABS | Motorcycle | Petrol | 2021 | ₹1,95,000 | Aarav Patel | `ENGMH149012345` | `VINMH14ROYAL003C` | Pimpri Chinchwad RTO |
| `DL01AB2345` | Tata Nexon EV | Empowered Plus Long Range | SUV | Electric | 2023 | ₹18,20,000 | Priya Sharma | `ENGDL012345671` | `VINDL01NEXON004D` | Mall Road RTO |
| `DL03CD6789` | Honda City | ZX i-VTEC CVT | Sedan | Petrol | 2022 | ₹14,20,000 | Priya Sharma | `ENGDL036789892` | `VINDL03HCITY005E` | Sheikh Sarai RTO |
| `DL08EF0123` | Ather 450X | Gen 3 Pro Pack | Motorcycle | Electric | 2023 | ₹1,45,000 | Priya Sharma | `ENGDL080123993` | `VINDL08ATHER006F` | Wazirpur RTO |
| `KA01AB3456` | Mahindra XUV700 | AX7 Luxury AWD Diesel AT | SUV | Diesel | 2023 | ₹24,80,000 | Rohan Iyer | `ENGKA013456774` | `VINKA01XUV70007G` | Koramangala RTO |
| `KA03CD7890` | Volkswagen Taigun | GT Plus 1.5 TSI DSG | SUV | Petrol | 2022 | ₹17,60,000 | Rohan Iyer | `ENGKA037890455` | `VINKA03TAIGUN08H` | Indiranagar RTO |
| `KA05EF1234` | Tata Tiago EV | XZ Plus Tech LUX | Hatchback | Electric | 2023 | ₹10,80,000 | Rohan Iyer | `ENGKA051234126` | `VINKA05TIAGO009J` | Jayanagar RTO |
| `TN01AB4567` | Toyota Innova Hycross | ZX (O) Strong Hybrid | SUV | Hybrid | 2024 | ₹31,50,000 | Ananya Sundaram | `ENGTN014567887` | `VINTN01INNOVA10K` | Chennai Central RTO |
| `TN07CD8901` | Hyundai i20 | Asta (O) 1.0 Turbo DCT | Hatchback | Petrol | 2021 | ₹9,80,000 | Ananya Sundaram | `ENGTN078901238` | `VINTN07HYNDI2011L` | Chennai South RTO |
| `TN09EF2345` | TVS Apache RR 310 | BTO Race Replica | Motorcycle | Petrol | 2022 | ₹2,65,000 | Ananya Sundaram | `ENGTN092345679` | `VINTN09TVS31012M` | Chennai West RTO |
| `RJ14AB0123` | Toyota Fortuner | 4X4 Legender AT Diesel | SUV | Diesel | 2023 | ₹44,50,000 | Vikram Rathore | `ENGRJ140123451` | `VINRJ14FORTUN13N` | Jaipur South RTO |
| `RJ45CD4567` | Mahindra Thar | LX 4X4 Hard Top Diesel MT | SUV | Diesel | 2022 | ₹15,80,000 | Vikram Rathore | `ENGRJ454567892` | `VINRJ45MTHAR014P` | Jaipur North RTO |
| `DL10GH4567` | Skoda Slavia | Style 1.5 TSI DSG | Sedan | Petrol | 2023 | ₹17,80,000 | Vikram Rathore | `ENGDL104567113` | `VINDL10SLAVIA15Q` | Rohini RTO |
| `MH04GH3456` | Kia Seltos | GTX Plus 1.5 Turbo DCT | SUV | Petrol | 2023 | ₹19,40,000 | Rajeshwari Kulkarni | `ENGMH043456224` | `VINMH04SELTOS16R` | Thane RTO |
| `MH47JK7890` | Honda Elevate | ZX CVT | SUV | Petrol | 2024 | ₹15,90,000 | Rajeshwari Kulkarni | `ENGMH477890555` | `VINMH47ELEVAT17S` | Borivali RTO |
| `KA51GH5678` | Maruti Suzuki Baleno | Alpha AMT | Hatchback | Petrol | 2022 | ₹8,90,000 | Rajeshwari Kulkarni | `ENGKA515678996` | `VINKA51BALENO18T` | Electronic City RTO |
| `WB02AB9012` | MG Motor Hector | Sharp Pro 2.0 Diesel MT | SUV | Diesel | 2023 | ₹21,80,000 | Amitav Banerjee | `ENGWB029012337` | `VINWB02MGHECT19U` | Kolkata South RTO |
| `WB20CD3456` | Hyundai Verna | SX (O) 1.5 Turbo DCT | Sedan | Petrol | 2023 | ₹16,80,000 | Amitav Banerjee | `ENGWB203456888` | `VINWB20HVERNA20V` | Alipore RTO |
| `TN22GH6789` | Yamaha YZF R15 V4 | Racing Blue Dual ABS | Motorcycle | Petrol | 2022 | ₹1,85,000 | Amitav Banerjee | `ENGTN226789449` | `VINTN22YAMR1521W` | Meenambakkam RTO |
| `MH12KL1122` | Tata Motors Harrier | Fearless Plus Dark AT | SUV | Diesel | 2024 | ₹24,90,000 | Sneha Deshmukh | `ENGMH121122771` | `VINMH12THARRI22X` | Pune RTO |
| `MH01MN3344` | Maruti Suzuki Brezza | ZXi Plus AT Dual Tone | SUV | Petrol | 2022 | ₹13,40,000 | Sneha Deshmukh | `ENGMH013344222` | `VINMH01BREZZA23Y` | Tardeo RTO |
| `GJ01AB5678` | KTM 390 Duke | Electronic Orange Gen 3 | Motorcycle | Petrol | 2023 | ₹3,10,000 | Sneha Deshmukh | `ENGGJ015678663` | `VINGJ01KTM39024Z` | Ahmedabad RTO |
| `GJ06CD9012` | Maruti Grand Vitara | Alpha Plus Hybrid e-CVT | SUV | Hybrid | 2023 | ₹19,80,000 | Chirag Mehta | `ENGGJ069012884` | `VINGJ06GVITAR25A` | Vadodara RTO |
| `GJ27EF3456` | Tata Motors Punch | Creative Flagship AMT | SUV | Petrol | 2022 | ₹9,20,000 | Chirag Mehta | `ENGGJ273456115` | `VINGJ27TPUNCH26B` | Ahmedabad East RTO |
| `UP32AB6789` | Kia Carens | Luxury Plus 1.5 Diesel AT | SUV | Diesel | 2023 | ₹18,90,000 | Neha Verma | `ENGUP326789446` | `VINUP32CARENS27C` | Lucknow RTO |
| `UP16CD0123` | Hyundai Venue | SX (O) 1.0 Turbo MT | SUV | Petrol | 2022 | ₹12,80,000 | Neha Verma | `ENGUP160123997` | `VINUP16HVENUE28D` | Noida RTO |
| `PB65AB2345` | Toyota Innova Crysta | 2.4 ZX 7 STR Diesel | SUV | Diesel | 2022 | ₹25,50,000 | Harpreet Singh | `ENGPB652345668` | `VINPB65CRYSTA29E` | Mohali RTO |
| `PB10CD6789` | Mahindra Scorpio-N | Z8L 4Xplor Diesel 4WD AT | SUV | Diesel | 2023 | ₹24,20,000 | Harpreet Singh | `ENGPB106789119` | `VINPB10SCORPN30F` | Ludhiana RTO |
| `KL01AB1234` | Honda Amaze | VX CVT 1.2 i-VTEC | Sedan | Petrol | 2021 | ₹8,90,000 | Deepa Nambiar | `ENGKL011234551` | `VINKL01HAMAZE31G` | Trivandrum RTO |
| `KL07CD5678` | MG Motor ZS EV | Exclusive Plus 50.3 kWh | SUV | Electric | 2023 | ₹25,20,000 | Deepa Nambiar | `ENGKL075678882` | `VINKL07MGZSEV32H` | Kochi RTO |
| `TS07AB7890` | BMW 3 Series | 330Li M Sport | Sedan | Petrol | 2023 | ₹59,50,000 | Arjun Reddy | `ENGTS077890113` | `VINTS07BMW33033J` | Khairatabad RTO |
| `TS09CD1234` | Hyundai Tucson | Signature 2.0 4WD AT | SUV | Diesel | 2023 | ₹34,20,000 | Arjun Reddy | `ENGTS091234774` | `VINTS09TUCSON34K` | Secunderabad RTO |
| `HR26AB8901` | Audi A4 | Technology 40 TFSI | Sedan | Petrol | 2023 | ₹48,50,000 | Pooja Choudhary | `ENGHR268901225` | `VINHR26AUDIA435L` | Gurugram North RTO |
| `HR51CD2345` | Maruti Suzuki Fronx | Alpha 1.0 Turbo AT | SUV | Petrol | 2023 | ₹12,40,000 | Pooja Choudhary | `ENGHR512345666` | `VINHR51MFRONX36M` | Faridabad RTO |
| `MP09AB3456` | Mahindra Bolero Neo | N10 (O) Diesel MT | SUV | Diesel | 2022 | ₹11,20,000 | Alok Tiwari | `ENGMP093456997` | `VINMP09BOLERO37N` | Indore RTO |
| `UP14EF4567` | Maruti Suzuki Ertiga | ZXi Plus AT Smart Hybrid | SUV | Hybrid | 2023 | ₹12,90,000 | Alok Tiwari | `ENGUP144567338` | `VINUP14ERTIGA38P` | Ghaziabad RTO |
