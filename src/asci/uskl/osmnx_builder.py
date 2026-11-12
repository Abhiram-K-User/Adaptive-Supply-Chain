"""
OSMnx-Compatible Corridor Network Builder & Offline Calibrator (PRD Sec. 3.2 & 4.2).
Builds the scaled 100-150 node, 300-500 directed edge South India automotive
logistics network (v1_corridor) with offline geodesic-circuity calibration and
optional live OpenStreetMap (osmnx) highway geometry snapping.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from asci.core.registry import CanonicalEntityRegistry, EntityType
from asci.uskl.graph_store import CorridorGraphStore

try:
    import osmnx as ox  # type: ignore
except ImportError:  # pragma: no cover - optional geo dependency
    ox = None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute great-circle distance in kilometers between two coordinates."""
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2.0) ** 2
    return 2.0 * r * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))


def _default_seeds_dir() -> Path:
    candidate = Path(__file__).resolve().parents[3] / "data" / "seeds"
    if candidate.exists():
        return candidate
    fallback = Path.cwd() / "data" / "seeds"
    if fallback.exists():
        return fallback
    return Path.cwd() / "asci-core" / "data" / "seeds"


class CorridorOSMnxBuilder:
    """
    Deterministic builder for the scaled South India corridor multigraph (v1_corridor).
    Preserves all 23 canonical Gate G0/G1 entities verbatim and scales to 118 nodes
    and ~380 directed road/rail links eliminating single-point topological bottlenecks.
    """

    @staticmethod
    def _extra_entities() -> list[dict[str, Any]]:
        """Return 95 canonical regional entities augmenting the 23 v0_core seeds to 118 nodes."""
        return [
            # +1 Port (8 total)
            {
                "id": "PORT_KARAIKAL",
                "name": "Karaikal Port Terminal",
                "entity_type": "PORT",
                "aliases": ["Karaikal Port", "MARG Karaikal", "Karaikal Terminal"],
                "latitude": 10.9032,
                "longitude": 79.8434,
                "region": "Tamil Nadu",
                "capacity_teu_per_day": 2500.0,
                "days_of_cover": None,
                "daily_demand_teu": None,
                "metadata": {"berths": 5, "rail_connected": True, "customs_edi": True},
            },
            # +3 ICDs (6 total)
            {
                "id": "ICD_HOSUR",
                "name": "CONCOR Hosur Multimodal ICD",
                "entity_type": "ICD",
                "aliases": ["Hosur ICD", "ICD Hosur", "Sipcot Hosur Railhead"],
                "latitude": 12.7120,
                "longitude": 77.8450,
                "region": "Tamil Nadu",
                "capacity_teu_per_day": 2200.0,
                "days_of_cover": None,
                "daily_demand_teu": None,
                "metadata": {"rail_lines": 4, "customs_office": True},
            },
            {
                "id": "ICD_KRISHNAPATNAM_RAIL",
                "name": "Krishnapatnam Rail Transshipment Yard",
                "entity_type": "ICD",
                "aliases": ["KPCL Rail Terminal", "Krishnapatnam ICD"],
                "latitude": 14.2350,
                "longitude": 80.0650,
                "region": "Andhra Pradesh",
                "capacity_teu_per_day": 2500.0,
                "days_of_cover": None,
                "daily_demand_teu": None,
                "metadata": {"rail_lines": 5, "customs_office": True},
            },
            {
                "id": "ICD_SALEM",
                "name": "Salem Multimodal Logistics ICD",
                "entity_type": "ICD",
                "aliases": ["Salem ICD", "ICD Salem", "CONCOR Salem"],
                "latitude": 11.6643,
                "longitude": 78.1460,
                "region": "Tamil Nadu",
                "capacity_teu_per_day": 2000.0,
                "days_of_cover": None,
                "daily_demand_teu": None,
                "metadata": {"rail_lines": 3, "customs_office": True},
            },
            # +24 Tier-1 supplier & assembly cluster PLANTs (30 total)
            *[
                {
                    "id": pid,
                    "name": pname,
                    "entity_type": "PLANT",
                    "aliases": aliases,
                    "latitude": lat,
                    "longitude": lon,
                    "region": region,
                    "capacity_teu_per_day": None,
                    "days_of_cover": cover,
                    "daily_demand_teu": demand,
                    "metadata": {"tier": "TIER1_CLUSTER", "oems": oems},
                }
                for pid, pname, aliases, lat, lon, region, demand, cover, oems in [
                    ("PLANT_MARAIMALAI", "Maraimalai Nagar Auto Ancillary Park", ["Maraimalai Nagar Plant", "Ford Vendor Park"], 12.7925, 80.0252, "Tamil Nadu", 350.0, 4.5, ["Tier-1 Chassis"]),
                    ("PLANT_AMBATTUR", "Ambattur Industrial Estate Auto Cluster", ["Ambattur Auto Estate", "Ambattur Plant"], 13.1067, 80.1610, "Tamil Nadu", 320.0, 4.0, ["Tier-1 Stamping"]),
                    ("PLANT_GUMMIDIPOONDI", "Gummidipoondi Automotive SIPCOT", ["Gummidipoondi Plant", "Gummidipoondi SIPCOT"], 13.4068, 80.1112, "Tamil Nadu", 300.0, 5.0, ["Tier-1 Forgings"]),
                    ("PLANT_IRUNGATTUKOTTAI", "Irungattukottai Ancillary Supplier Hub", ["Irungattukottai Park", "SIPCOT Irungattukottai"], 12.9950, 79.9920, "Tamil Nadu", 360.0, 4.0, ["Hyundai Ancillary"]),
                    ("PLANT_VALLAM_VADAGAL", "Vallam Vadagal EV & Aero Park", ["Vallam Vadagal", "SIPCOT Vallam"], 12.8850, 79.9080, "Tamil Nadu", 310.0, 4.5, ["EV Powertrain"]),
                    ("PLANT_CHENGALPATTU", "Chengalpattu Mahindra Auto Hub", ["Chengalpattu Plant", "MWC Chengalpattu"], 12.7350, 79.9980, "Tamil Nadu", 340.0, 5.0, ["Mahindra Ancillary"]),
                    ("PLANT_THIRUVALLUR", "Thiruvallur Commercial Chassis Hub", ["Thiruvallur Plant", "Kakkalur Auto Hub"], 13.1430, 79.9080, "Tamil Nadu", 280.0, 4.5, ["Commercial Axle"]),
                    ("PLANT_CHEYYAR", "Cheyyar Industrial Auto Components", ["Cheyyar SIPCOT", "Cheyyar Plant"], 12.6600, 79.5400, "Tamil Nadu", 260.0, 5.5, ["Braking Assemblies"]),
                    ("PLANT_KRISHNAGIRI_TIER1", "Krishnagiri EV Two-Wheeler Cluster", ["Krishnagiri EV Hub", "Bargur Auto Park"], 12.5480, 78.3150, "Tamil Nadu", 320.0, 4.5, ["EV Battery Pack"]),
                    ("PLANT_PEENYA", "Peenya Precision Auto Engineering Hub", ["Peenya Industrial Hub", "Peenya Plant"], 13.0285, 77.5197, "Karnataka", 350.0, 4.0, ["Bosch Peenya"]),
                    ("PLANT_BOMMASANDRA", "Bommasandra Auto Electronics Cluster", ["Bommasandra Plant", "Jigani Auto Hub"], 12.8162, 77.6975, "Karnataka", 340.0, 4.5, ["ECU Tier-1"]),
                    ("PLANT_HAROHALLI", "Harohalli Phase-2 Supplier Park", ["Harohalli Auto Park", "Harohalli KIADB"], 12.6950, 77.4680, "Karnataka", 280.0, 5.0, ["Toyota Vendor Park"]),
                    ("PLANT_NARASAPURA", "Narasapura Kolar Auto Assembly Hub", ["Narasapura KIADB", "Kolar Auto Hub"], 13.1460, 78.0050, "Karnataka", 330.0, 4.5, ["Honda/Scania Tier-1"]),
                    ("PLANT_VEMAGAL", "Vemagal Tier-1 Driveline Cluster", ["Vemagal Industrial Area", "Vemagal Plant"], 13.1860, 78.0340, "Karnataka", 260.0, 5.0, ["Driveline Tiers"]),
                    ("PLANT_TUMAKURU", "Tumakuru NIMZ Component Park", ["Tumakuru Auto Hub", "Vasanthanarasapura"], 13.4280, 77.0150, "Karnataka", 290.0, 5.5, ["Precision Forgings"]),
                    ("PLANT_DOBBASPET", "Dobbaspet Automotive Castings Hub", ["Dobbaspet KIADB", "Dobbaspet Plant"], 13.2340, 77.2350, "Karnataka", 250.0, 5.0, ["Iron Castings"]),
                    ("PLANT_TADA", "Tada Automotive & Wiring Harness Hub", ["Tada Industrial Park", "Tada Plant"], 13.5910, 80.0320, "Andhra Pradesh", 280.0, 5.0, ["Wiring Harness"]),
                    ("PLANT_NAIDUPETA", "Naidupeta Multi-Product Auto SEZ", ["Naidupeta SEZ", "Naidupeta Plant"], 13.9020, 79.8950, "Andhra Pradesh", 270.0, 5.5, ["Tyre & Alloy"]),
                    ("PLANT_TIRUPATI_ELECTRONICS", "Tirupati EV Electronics Park", ["Tirupati EMC", "Renigunta Auto Electronics"], 13.6288, 79.5420, "Andhra Pradesh", 300.0, 4.5, ["EV Sensors"]),
                    ("PLANT_CHITTOOR_AUTO", "Chittoor Foundry & Harness Plant", ["Chittoor Industrial Hub", "Chittoor Auto"], 13.2040, 79.0920, "Andhra Pradesh", 250.0, 5.5, ["Fasteners & Wire"]),
                    ("PLANT_NELLORE_TIER1", "Nellore Marine-Auto Fabrication Hub", ["Nellore Industrial Estate", "Nellore Auto"], 14.4426, 79.9865, "Andhra Pradesh", 270.0, 5.0, ["Chassis Weldments"]),
                    ("PLANT_KINATHUKADAVU", "Kinathukadavu Foundry & Forging Hub", ["Kinathukadavu Auto", "Pollachi Tier-1"], 10.8220, 77.0180, "Tamil Nadu", 290.0, 5.0, ["Powertrain Castings"]),
                    ("PLANT_SALEM_STEEL", "Salem Auto Steel & Bearing Plant", ["Salem Steel Auto", "Mettur Auto Bearing"], 11.6750, 78.0820, "Tamil Nadu", 310.0, 5.5, ["Special Alloy Steel"]),
                    ("PLANT_PALAKKAD_COMPONENTS", "Palakkad KINFRA Auto Component Park", ["Palakkad KINFRA", "Kanjikode Auto Hub"], 10.7867, 76.7420, "Kerala", 260.0, 5.5, ["Fluid Valves"]),
                ]
            ],
            # +19 CFS / Warehousing Hubs (22 total)
            *[
                {
                    "id": cid,
                    "name": cname,
                    "entity_type": "CFS",
                    "aliases": aliases,
                    "latitude": lat,
                    "longitude": lon,
                    "region": region,
                    "capacity_teu_per_day": cap,
                    "days_of_cover": None,
                    "daily_demand_teu": None,
                    "metadata": {"yard_capacity_teu": int(cap * 4)},
                }
                for cid, cname, aliases, lat, lon, region, cap in [
                    ("CFS_PONNERI", "Ponneri North Gateway CFS", ["Ponneri CFS"], 13.3370, 80.1940, "Tamil Nadu", 2800.0),
                    ("CFS_MINJUR", "Minjur Outer Harbour CFS", ["Minjur CFS"], 13.2780, 80.2640, "Tamil Nadu", 2600.0),
                    ("CFS_SRIPERUMBUDUR", "Sriperumbudur Bonded Logistics CFS", ["Sriperumbudur CFS"], 12.9680, 79.9150, "Tamil Nadu", 3200.0),
                    ("CFS_ORAGADAM", "Oragadam JIT Consolidation CFS", ["Oragadam CFS"], 12.8420, 79.9220, "Tamil Nadu", 3200.0),
                    ("CFS_MANALI", "Manali Industrial CFS", ["Manali CFS"], 13.1680, 80.2580, "Tamil Nadu", 2800.0),
                    ("CFS_KRISHNAPATNAM", "Krishnapatnam Port Feeder CFS", ["Krishnapatnam CFS"], 14.2560, 80.0980, "Andhra Pradesh", 3400.0),
                    ("CFS_SULLURPETA", "Sullurpeta Border Customs CFS", ["Sullurpeta CFS"], 13.7020, 80.0220, "Andhra Pradesh", 2500.0),
                    ("CFS_KARAIKAL", "Karaikal Coastal Container CFS", ["Karaikal CFS"], 10.9150, 79.8250, "Tamil Nadu", 2400.0),
                    ("CFS_PONDICHERRY", "Puducherry NH32 Feeder CFS", ["Pondicherry CFS"], 11.9416, 79.8083, "Tamil Nadu", 2200.0),
                    ("CFS_TUTICORIN_BOND", "Tuticorin VOC Outer Bonded CFS", ["Tuticorin CFS"], 8.7890, 78.1450, "Tamil Nadu", 2600.0),
                    ("CFS_MADURAI_INLAND", "Madurai Kapalur Consolidation CFS", ["Madurai CFS"], 9.8650, 78.0350, "Tamil Nadu", 2400.0),
                    ("CFS_COCHIN_VALLARPADAM", "Cochin Ernakulam Feeder CFS", ["Cochin Feeder CFS"], 9.9920, 76.3120, "Kerala", 3000.0),
                    ("CFS_PALAKKAD_FREIGHT", "Palakkad Walayar Border CFS", ["Palakkad CFS"], 10.8180, 76.8250, "Kerala", 2500.0),
                    ("CFS_COIMBATORE_NEELAMBUR", "Coimbatore Neelambur Auto CFS", ["Neelambur CFS"], 11.0680, 77.0880, "Tamil Nadu", 2800.0),
                    ("CFS_SALEM_LOGISTICS", "Salem Sankari Road Auto CFS", ["Salem CFS"], 11.6480, 78.0950, "Tamil Nadu", 2600.0),
                    ("CFS_HOSUR_LOGISTICS", "Hosur Zuzuvadi Freight CFS", ["Hosur CFS"], 12.7650, 77.8020, "Tamil Nadu", 3000.0),
                    ("CFS_BOMMASANDRA", "Bommasandra Hebbagodi Auto CFS", ["Bommasandra CFS"], 12.8280, 77.6850, "Karnataka", 2600.0),
                    ("CFS_NELAMANGALA", "Nelamangala Tumkur Road CFS", ["Nelamangala CFS"], 13.0990, 77.3920, "Karnataka", 2800.0),
                    ("CFS_MANGALORE_PANAMBUR", "Mangalore Baikampady Export CFS", ["Panambur CFS"], 12.9480, 74.8250, "Karnataka", 2400.0),
                ]
            ],
            # +38 Corridor Junctions (42 junctions) + 10 Outbound Gateways (52 JUNCTIONs total = 118 nodes total)
            *[
                {
                    "id": jid,
                    "name": jname,
                    "entity_type": "CORRIDOR_JUNCTION",
                    "aliases": [jname],
                    "latitude": lat,
                    "longitude": lon,
                    "region": region,
                    "capacity_teu_per_day": cap,
                    "days_of_cover": None,
                    "daily_demand_teu": None,
                    "metadata": meta,
                }
                for jid, jname, lat, lon, region, cap, meta in [
                    ("JUNCTION_GUMMIDIPOONDI", "Gummidipoondi NH16 Interchange", 13.4120, 80.1250, "Tamil Nadu", 5500.0, {"highway": "NH16"}),
                    ("JUNCTION_TADA", "Tada Border NH16 Node", 13.5880, 80.0250, "Andhra Pradesh", 5000.0, {"highway": "NH16"}),
                    ("JUNCTION_NAIDUPETA", "Naidupeta NH16/NH71 Spur", 13.8950, 79.9080, "Andhra Pradesh", 5000.0, {"highway": "NH16/NH71"}),
                    ("JUNCTION_GUDUR", "Gudur Nellore Rail-Road Crossing", 14.1480, 79.8520, "Andhra Pradesh", 5000.0, {"highway": "NH16"}),
                    ("JUNCTION_TIRUVALLUR", "Tiruvallur NH716 Node", 13.1380, 79.9150, "Tamil Nadu", 4500.0, {"highway": "NH716"}),
                    ("JUNCTION_TAMBARAM", "Tambaram Chennai Outer Ring Node", 12.9249, 80.1000, "Tamil Nadu", 5500.0, {"highway": "NH32/ORR"}),
                    ("JUNCTION_CHENGALPATTU", "Chengalpattu GST Road Interchange", 12.6921, 79.9760, "Tamil Nadu", 5000.0, {"highway": "NH32"}),
                    ("JUNCTION_TINDIVANAM", "Tindivanam NH32/NH77 Junction", 12.2300, 79.6500, "Tamil Nadu", 4500.0, {"highway": "NH32"}),
                    ("JUNCTION_VILLUPURAM", "Villupuram Highway Bifurcation", 11.9401, 79.4861, "Tamil Nadu", 4500.0, {"highway": "NH32/NH38"}),
                    ("JUNCTION_ULUNDURPET", "Ulundurpet Central TN Node", 11.6900, 79.2900, "Tamil Nadu", 4500.0, {"highway": "NH38/NH79"}),
                    ("JUNCTION_TRICHY", "Tiruchirappalli Central Corridor Hub", 10.7905, 78.7047, "Tamil Nadu", 5000.0, {"highway": "NH38/NH83"}),
                    ("JUNCTION_DINDIGUL", "Dindigul NH44/NH83 Junction", 10.3673, 77.9803, "Tamil Nadu", 4500.0, {"highway": "NH44"}),
                    ("JUNCTION_MADURAI", "Madurai Southern Logistics Ring", 9.9252, 78.1198, "Tamil Nadu", 4500.0, {"highway": "NH44"}),
                    ("JUNCTION_TIRUNELVELI", "Tirunelveli Tuticorin Feeder Hub", 8.7139, 77.7567, "Tamil Nadu", 4000.0, {"highway": "NH44"}),
                    ("JUNCTION_KARUR", "Karur Textile-Auto Corridor Node", 10.9601, 78.0766, "Tamil Nadu", 4500.0, {"highway": "NH44/NH81"}),
                    ("JUNCTION_ERODE", "Erode Perundurai NH544 Interchange", 11.3410, 77.7172, "Tamil Nadu", 4800.0, {"highway": "NH544"}),
                    ("JUNCTION_AVINASHI", "Avinashi Coimbatore Bypass", 11.1920, 77.2680, "Tamil Nadu", 4800.0, {"highway": "NH544"}),
                    ("JUNCTION_POLLACHI", "Pollachi Valparai Road Node", 10.6580, 77.0080, "Tamil Nadu", 4000.0, {"highway": "NH83"}),
                    ("JUNCTION_WALAYAR", "Walayar TN-KL Freight Checkpost", 10.8380, 76.8450, "Kerala", 4500.0, {"highway": "NH544"}),
                    ("JUNCTION_THRISSUR", "Thrissur Central Kerala NH544", 10.5276, 76.2144, "Kerala", 4500.0, {"highway": "NH544/NH66"}),
                    ("JUNCTION_PALAKKAD", "Palakkad Junction North Pass", 10.7780, 76.6540, "Kerala", 4500.0, {"highway": "NH544"}),
                    ("JUNCTION_SALEM_BYPASS", "Salem NH44/NH544 Interchange", 11.6520, 78.1580, "Tamil Nadu", 5500.0, {"highway": "NH44/NH544"}),
                    ("JUNCTION_DHARMAPURI", "Dharmapuri NH44 Freight Link", 12.1211, 78.1582, "Tamil Nadu", 5000.0, {"highway": "NH44"}),
                    ("JUNCTION_AMBUR", "Ambur Palar Valley NH48 Node", 12.7900, 78.7160, "Tamil Nadu", 5000.0, {"highway": "NH48"}),
                    ("JUNCTION_WALAJAPET", "Walajapet Tolls NH48/NH40", 12.9270, 79.3660, "Tamil Nadu", 5500.0, {"highway": "NH48"}),
                    ("JUNCTION_KOLAR", "Kolar NH75 Express Interchange", 13.1362, 78.1292, "Karnataka", 5000.0, {"highway": "NH75"}),
                    ("JUNCTION_MULBAGAL", "Mulbagal KA-AP Border NH75", 13.1640, 78.3950, "Karnataka", 4800.0, {"highway": "NH75"}),
                    ("JUNCTION_HOSKOTE", "Hoskote East Bengaluru Ring", 13.0700, 77.7980, "Karnataka", 5500.0, {"highway": "NH75/STRR"}),
                    ("JUNCTION_NELAMANGALA", "Nelamangala NH48/NH75 Spine", 13.0950, 77.3880, "Karnataka", 5500.0, {"highway": "NH48/NH75"}),
                    ("JUNCTION_TUMAKURU_NH48", "Tumakuru North-West Bypass", 13.3392, 77.1140, "Karnataka", 5000.0, {"highway": "NH48"}),
                    ("JUNCTION_HASSAN", "Hassan Shiradi Ghat Feeder", 13.0033, 76.1004, "Karnataka", 4500.0, {"highway": "NH75"}),
                    ("JUNCTION_KUNIGAL", "Kunigal Hassan-Bengaluru Spur", 13.0220, 77.0250, "Karnataka", 4500.0, {"highway": "NH75"}),
                    ("JUNCTION_MYSURU_RING", "Mysuru Peripheral Highway Node", 12.2958, 76.6394, "Karnataka", 4200.0, {"highway": "NH275"}),
                    ("JUNCTION_MANDYA", "Mandya Expressway Interchange", 12.5218, 76.8951, "Karnataka", 4200.0, {"highway": "NH275"}),
                    ("JUNCTION_RAMANAGARA", "Ramanagara Bidadi Feeder Node", 12.7150, 77.2810, "Karnataka", 4500.0, {"highway": "NH275/STRR"}),
                    ("JUNCTION_ATTIBELE", "Attibele KA-TN Border NH44", 12.7780, 77.7720, "Karnataka", 5500.0, {"highway": "NH44"}),
                    ("JUNCTION_ELECTRONIC_CITY", "Electronic City NICE Junction", 12.8452, 77.6602, "Karnataka", 5500.0, {"highway": "NH44/NICE"}),
                    ("JUNCTION_RENIGUNTA", "Renigunta Rail-Highway Triangle", 13.6350, 79.5120, "Andhra Pradesh", 4800.0, {"highway": "NH71/NH716"}),
                    # 10 Outbound Market Gateways (tagged role="outbound_gateway")
                    ("OUTBOUND_HYDERABAD_NH44", "Hyderabad North Outbound Gateway", 13.9500, 77.6500, "Andhra Pradesh", 5000.0, {"role": "outbound_gateway", "corridor": "North-Central India"}),
                    ("OUTBOUND_PUNE_MUMBAI_NH48", "Pune-Mumbai NH48 Outbound Gateway", 13.8500, 76.4500, "Karnataka", 5000.0, {"role": "outbound_gateway", "corridor": "West India Auto Belt"}),
                    ("OUTBOUND_VIJAYAWADA_NH16", "Vijayawada-Vizag NH16 Gateway", 14.7500, 80.0200, "Andhra Pradesh", 5000.0, {"role": "outbound_gateway", "corridor": "East Coast NH16"}),
                    ("OUTBOUND_TIRUPATI_GATE", "Tirupati Rayalaseema Market Gate", 13.6900, 79.3500, "Andhra Pradesh", 4000.0, {"role": "outbound_gateway", "corridor": "Rayalaseema"}),
                    ("OUTBOUND_MANGALORE_COAST", "Konkan West Export Coastal Gate", 13.3500, 74.7500, "Karnataka", 4000.0, {"role": "outbound_gateway", "corridor": "Konkan Rail/Port"}),
                    ("OUTBOUND_COCHIN_EXPORT_GATE", "Vallarpadam Arabian Sea Gate", 9.9600, 76.2200, "Kerala", 4500.0, {"role": "outbound_gateway", "corridor": "Europe/Middle East Sea"}),
                    ("OUTBOUND_TUTICORIN_DEEPSEA", "Tuticorin South Sea Export Gate", 8.7300, 78.2200, "Tamil Nadu", 4000.0, {"role": "outbound_gateway", "corridor": "Colombo/East Africa Feeder"}),
                    ("OUTBOUND_CHENNAI_EXPORT_GATE", "Ennore-Chennai Bay Export Gate", 13.1500, 80.3500, "Tamil Nadu", 6000.0, {"role": "outbound_gateway", "corridor": "APAC/ASEAN Maritime"}),
                    ("OUTBOUND_BENGALURU_NORTH_AIR", "Devanahalli Aero-Auto Express Gate", 13.2100, 77.7100, "Karnataka", 4500.0, {"role": "outbound_gateway", "corridor": "Express Assembly Parts"}),
                    ("OUTBOUND_COIMBATORE_WEST_GATE", "Coimbatore West Industrial Gate", 11.0400, 76.8900, "Tamil Nadu", 4000.0, {"role": "outbound_gateway", "corridor": "West TN/KL Market"}),
                ]
            ],
        ]

    @staticmethod
    def _edge_specs() -> list[tuple[str, str, str, str, float]]:
        """
        Return directed corridor links as (source, target, key, mode, capacity_teu_per_day).
        Distances, transit times, and costs are calibrated physically from coordinates.
        """
        specs: list[tuple[str, str, str, str, float]] = [
            # Coastal Port -> CFS/ICD/Junction Primary Outflows
            ("PORT_KAMARAJAR", "CFS_MINJUR", "ROAD_0", "ROAD", 3200.0),
            ("PORT_KAMARAJAR", "CFS_PONNERI", "ROAD_1", "ROAD", 2800.0),
            ("PORT_KAMARAJAR", "JUNCTION_GUMMIDIPOONDI", "ROAD_NH16", "ROAD", 3200.0),
            ("PORT_KAMARAJAR", "ICD_KRISHNAPATNAM_RAIL", "RAIL_COASTAL", "RAIL", 2200.0),
            ("PORT_KAMARAJAR", "ICD_HOSUR", "RAIL_BLOCK", "RAIL", 1800.0),
            ("PORT_KATTUPALLI", "CFS_MINJUR", "ROAD_0", "ROAD", 2600.0),
            ("PORT_KATTUPALLI", "CFS_PONNERI", "ROAD_1", "ROAD", 2600.0),
            ("PORT_KATTUPALLI", "ICD_TONDIARPET", "RAIL_0", "RAIL", 2000.0),
            ("PORT_KATTUPALLI", "JUNCTION_GUMMIDIPOONDI", "ROAD_NH16", "ROAD", 2800.0),
            ("PORT_CHENNAI", "CFS_MANALI", "ROAD_1", "ROAD", 3200.0),
            ("PORT_CHENNAI", "JUNCTION_TAMBARAM", "ROAD_BYPASS", "ROAD", 3400.0),
            ("PORT_CHENNAI", "ICD_HOSUR", "RAIL_BLOCK", "RAIL", 2000.0),
            ("PORT_CHENNAI", "ICD_SALEM", "RAIL_SOUTH", "RAIL", 1800.0),
            ("PORT_KRISHNAPATNAM", "CFS_KRISHNAPATNAM", "ROAD_LOCAL", "ROAD", 3500.0),
            ("PORT_KRISHNAPATNAM", "ICD_KRISHNAPATNAM_RAIL", "RAIL_0", "RAIL", 2800.0),
            ("PORT_KRISHNAPATNAM", "JUNCTION_GUDUR", "ROAD_SPUR", "ROAD", 3200.0),
            ("PORT_KARAIKAL", "CFS_KARAIKAL", "ROAD_0", "ROAD", 2400.0),
            ("PORT_KARAIKAL", "CFS_PONDICHERRY", "ROAD_EC", "ROAD", 2000.0),
            ("PORT_KARAIKAL", "JUNCTION_TRICHY", "RAIL_BRANCH", "RAIL", 1800.0),
            ("PORT_VOC", "CFS_TUTICORIN_BOND", "ROAD_0", "ROAD", 2800.0),
            ("PORT_VOC", "JUNCTION_TIRUNELVELI", "ROAD_NH44", "ROAD", 2400.0),
            ("PORT_VOC", "JUNCTION_MADURAI", "RAIL_SOUTH", "RAIL", 1800.0),
            ("PORT_COCHIN", "CFS_COCHIN_VALLARPADAM", "ROAD_0", "ROAD", 3200.0),
            ("PORT_COCHIN", "JUNCTION_THRISSUR", "ROAD_NH544", "ROAD", 3000.0),
            ("PORT_COCHIN", "JUNCTION_PALAKKAD", "RAIL_WEST", "RAIL", 2000.0),
            ("PORT_NEW_MANGALORE", "CFS_MANGALORE_PANAMBUR", "ROAD_0", "ROAD", 2500.0),
            ("PORT_NEW_MANGALORE", "JUNCTION_HASSAN", "ROAD_NH75", "ROAD", 2400.0),
            ("PORT_NEW_MANGALORE", "ICD_HOSUR", "RAIL_GHAT", "RAIL", 1500.0),
            # Chennai / Ennore CFS & Junction Ring
            ("CFS_ENNORE_LOGISTICS", "CFS_MANALI", "ROAD_0", "ROAD", 2500.0),
            ("CFS_ENNORE_LOGISTICS", "CFS_SRIPERUMBUDUR", "ROAD_OR", "ROAD", 2500.0),
            ("CFS_MINJUR", "CFS_PONNERI", "ROAD_0", "ROAD", 2500.0),
            ("CFS_MINJUR", "CFS_MANALI", "ROAD_0", "ROAD", 2500.0),
            ("CFS_PONNERI", "JUNCTION_GUMMIDIPOONDI", "ROAD_0", "ROAD", 2800.0),
            ("CFS_PONNERI", "PLANT_GUMMIDIPOONDI", "ROAD_0", "ROAD", 2000.0),
            ("CFS_PONNERI", "PLANT_AMBATTUR", "ROAD_0", "ROAD", 2000.0),
            ("CFS_MANALI", "CFS_CHENNAI_CENTRAL", "ROAD_0", "ROAD", 3000.0),
            ("CFS_MANALI", "PLANT_AMBATTUR", "ROAD_0", "ROAD", 2200.0),
            ("CFS_MANALI", "JUNCTION_TIRUVALLUR", "ROAD_0", "ROAD", 2600.0),
            ("CFS_CHENNAI_CENTRAL", "CFS_SRIPERUMBUDUR", "ROAD_0", "ROAD", 2800.0),
            ("CFS_CHENNAI_CENTRAL", "CFS_ORAGADAM", "ROAD_0", "ROAD", 2800.0),
            ("CFS_CHENNAI_CENTRAL", "PLANT_AMBATTUR", "ROAD_0", "ROAD", 2200.0),
            ("CFS_CHENNAI_CENTRAL", "JUNCTION_TAMBARAM", "ROAD_0", "ROAD", 2800.0),
            ("ICD_TONDIARPET", "CFS_MANALI", "ROAD_0", "ROAD", 2400.0),
            ("ICD_TONDIARPET", "CFS_SRIPERUMBUDUR", "ROAD_0", "ROAD", 2500.0),
            ("ICD_TONDIARPET", "ICD_HOSUR", "RAIL_CONCOR", "RAIL", 2000.0),
            ("ICD_TONDIARPET", "ICD_SALEM", "RAIL_CONCOR", "RAIL", 1800.0),
            ("ICD_TONDIARPET", "ICD_KRISHNAPATNAM_RAIL", "RAIL_NORTH", "RAIL", 2200.0),
            ("JUNCTION_TAMBARAM", "CFS_ORAGADAM", "ROAD_0", "ROAD", 3000.0),
            ("JUNCTION_TAMBARAM", "JUNCTION_CHENGALPATTU", "ROAD_NH32", "ROAD", 4000.0),
            ("JUNCTION_TAMBARAM", "PLANT_MARAIMALAI", "ROAD_NH32", "ROAD", 2200.0),
            ("JUNCTION_CHENGALPATTU", "PLANT_MARAIMALAI", "ROAD_0", "ROAD", 2200.0),
            ("JUNCTION_CHENGALPATTU", "PLANT_CHENGALPATTU", "ROAD_0", "ROAD", 2200.0),
            ("JUNCTION_CHENGALPATTU", "CFS_ORAGADAM", "ROAD_SPUR", "ROAD", 2500.0),
            ("JUNCTION_CHENGALPATTU", "PLANT_CHEYYAR", "ROAD_0", "ROAD", 2000.0),
            ("JUNCTION_CHENGALPATTU", "JUNCTION_TINDIVANAM", "ROAD_NH32", "ROAD", 3800.0),
            ("JUNCTION_TIRUVALLUR", "PLANT_THIRUVALLUR", "ROAD_0", "ROAD", 2200.0),
            ("JUNCTION_TIRUVALLUR", "CFS_SRIPERUMBUDUR", "ROAD_0", "ROAD", 2600.0),
            ("JUNCTION_TIRUVALLUR", "JUNCTION_RANIPET", "ROAD_NH716", "ROAD", 3200.0),
            ("JUNCTION_TIRUVALLUR", "JUNCTION_RENIGUNTA", "RAIL_TRUNK", "RAIL", 2200.0),
            # North TN -> AP Corridor (Eliminating Sri City Single-Point Bottleneck)
            ("JUNCTION_GUMMIDIPOONDI", "PLANT_GUMMIDIPOONDI", "ROAD_LOCAL", "ROAD", 2000.0),
            ("JUNCTION_GUMMIDIPOONDI", "JUNCTION_TADA", "ROAD_NH16", "ROAD", 4200.0),
            ("JUNCTION_GUMMIDIPOONDI", "CFS_SULLURPETA", "ROAD_NH16", "ROAD", 3200.0),
            ("JUNCTION_TADA", "PLANT_SRICITY", "ROAD_DIRECT", "ROAD", 2600.0),
            ("JUNCTION_TADA", "PLANT_TADA", "ROAD_0", "ROAD", 2200.0),
            ("JUNCTION_TADA", "CFS_SULLURPETA", "ROAD_NH16", "ROAD", 3500.0),
            ("CFS_SULLURPETA", "PLANT_SRICITY", "ROAD_FEED", "ROAD", 2200.0),
            ("CFS_SULLURPETA", "PLANT_TADA", "ROAD_0", "ROAD", 2000.0),
            ("CFS_SULLURPETA", "JUNCTION_NAIDUPETA", "ROAD_NH16", "ROAD", 3500.0),
            ("CFS_SULLURPETA", "PLANT_NAIDUPETA", "ROAD_0", "ROAD", 2000.0),
            ("JUNCTION_NAIDUPETA", "PLANT_NAIDUPETA", "ROAD_LOCAL", "ROAD", 2000.0),
            ("JUNCTION_NAIDUPETA", "JUNCTION_GUDUR", "ROAD_NH16", "ROAD", 3800.0),
            ("JUNCTION_NAIDUPETA", "JUNCTION_RENIGUNTA", "ROAD_NH71", "ROAD", 3200.0),
            ("JUNCTION_GUDUR", "CFS_KRISHNAPATNAM", "ROAD_0", "ROAD", 3400.0),
            ("JUNCTION_GUDUR", "PLANT_NELLORE_TIER1", "ROAD_NH16", "ROAD", 2200.0),
            ("JUNCTION_GUDUR", "JUNCTION_NAIDUPETA", "ROAD_NH16_SB", "ROAD", 3800.0),
            ("CFS_KRISHNAPATNAM", "ICD_KRISHNAPATNAM_RAIL", "ROAD_LOCAL", "ROAD", 3000.0),
            ("CFS_KRISHNAPATNAM", "PLANT_NELLORE_TIER1", "ROAD_0", "ROAD", 2200.0),
            ("CFS_KRISHNAPATNAM", "JUNCTION_GUDUR", "ROAD_0", "ROAD", 3400.0),
            ("CFS_KRISHNAPATNAM", "CFS_SULLURPETA", "ROAD_NH16_SB", "ROAD", 3000.0),
            ("ICD_KRISHNAPATNAM_RAIL", "JUNCTION_RENIGUNTA", "RAIL_AP", "RAIL", 2400.0),
            ("ICD_KRISHNAPATNAM_RAIL", "JUNCTION_CHITTOOR", "ROAD_NH71", "ROAD", 2600.0),
            ("ICD_KRISHNAPATNAM_RAIL", "PLANT_TIRUPATI_ELECTRONICS", "RAIL_FEED", "RAIL", 1800.0),
            ("JUNCTION_RENIGUNTA", "PLANT_TIRUPATI_ELECTRONICS", "ROAD_0", "ROAD", 2200.0),
            ("JUNCTION_RENIGUNTA", "PLANT_SRICITY", "ROAD_AP_BYPASS", "ROAD", 2200.0),
            ("JUNCTION_RENIGUNTA", "JUNCTION_CHITTOOR", "ROAD_NH40", "ROAD", 3200.0),
            ("JUNCTION_RENIGUNTA", "JUNCTION_TADA", "ROAD_SPUR", "ROAD", 2800.0),
            # Sriperumbudur - Oragadam Tier-1 Manufacturing Web
            ("CFS_SRIPERUMBUDUR", "PLANT_SRIPERUMBUDUR", "ROAD_0", "ROAD", 3200.0),
            ("CFS_SRIPERUMBUDUR", "PLANT_IRUNGATTUKOTTAI", "ROAD_0", "ROAD", 2200.0),
            ("CFS_SRIPERUMBUDUR", "PLANT_VALLAM_VADAGAL", "ROAD_0", "ROAD", 2200.0),
            ("CFS_SRIPERUMBUDUR", "PLANT_THIRUVALLUR", "ROAD_0", "ROAD", 2000.0),
            ("CFS_SRIPERUMBUDUR", "JUNCTION_RANIPET", "ROAD_NH48", "ROAD", 3600.0),
            ("CFS_ORAGADAM", "PLANT_ORAGADAM", "ROAD_0", "ROAD", 3200.0),
            ("CFS_ORAGADAM", "PLANT_VALLAM_VADAGAL", "ROAD_0", "ROAD", 2200.0),
            ("CFS_ORAGADAM", "PLANT_CHENGALPATTU", "ROAD_0", "ROAD", 2200.0),
            ("CFS_ORAGADAM", "PLANT_CHEYYAR", "ROAD_0", "ROAD", 2000.0),
            ("CFS_ORAGADAM", "JUNCTION_WALAJAPET", "ROAD_NH48", "ROAD", 3400.0),
            ("PLANT_SRIPERUMBUDUR", "PLANT_IRUNGATTUKOTTAI", "ROAD_LOCAL", "ROAD", 2200.0),
            ("PLANT_ORAGADAM", "PLANT_MARAIMALAI", "ROAD_LOCAL", "ROAD", 2200.0),
            # Karaikal / Pondicherry / Trichy / Madurai / VOC South Corridor
            ("CFS_KARAIKAL", "CFS_PONDICHERRY", "ROAD_0", "ROAD", 2400.0),
            ("CFS_KARAIKAL", "JUNCTION_TRICHY", "ROAD_NH83", "ROAD", 2800.0),
            ("CFS_PONDICHERRY", "JUNCTION_TINDIVANAM", "ROAD_0", "ROAD", 2600.0),
            ("CFS_PONDICHERRY", "JUNCTION_VILLUPURAM", "ROAD_0", "ROAD", 2600.0),
            ("JUNCTION_TINDIVANAM", "JUNCTION_CHENGALPATTU", "ROAD_NH32_NB", "ROAD", 3600.0),
            ("JUNCTION_TINDIVANAM", "JUNCTION_VILLUPURAM", "ROAD_NH32", "ROAD", 3800.0),
            ("JUNCTION_VILLUPURAM", "JUNCTION_ULUNDURPET", "ROAD_NH38", "ROAD", 3800.0),
            ("JUNCTION_VILLUPURAM", "JUNCTION_TINDIVANAM", "ROAD_NH32_NB", "ROAD", 3600.0),
            ("JUNCTION_ULUNDURPET", "JUNCTION_SALEM_BYPASS", "ROAD_NH79", "ROAD", 3400.0),
            ("JUNCTION_ULUNDURPET", "JUNCTION_TRICHY", "ROAD_NH38", "ROAD", 3600.0),
            ("JUNCTION_ULUNDURPET", "JUNCTION_VILLUPURAM", "ROAD_NH38_NB", "ROAD", 3600.0),
            ("JUNCTION_TRICHY", "JUNCTION_KARUR", "ROAD_NH81", "ROAD", 3600.0),
            ("JUNCTION_TRICHY", "JUNCTION_DINDIGUL", "ROAD_NH83", "ROAD", 3400.0),
            ("JUNCTION_TRICHY", "JUNCTION_ULUNDURPET", "ROAD_NH38_NB", "ROAD", 3400.0),
            ("JUNCTION_KARUR", "JUNCTION_ERODE", "ROAD_NH81", "ROAD", 3400.0),
            ("JUNCTION_KARUR", "JUNCTION_SALEM_BYPASS", "ROAD_NH44", "ROAD", 3400.0),
            ("JUNCTION_KARUR", "JUNCTION_DINDIGUL", "ROAD_NH44_SB", "ROAD", 3200.0),
            ("JUNCTION_DINDIGUL", "JUNCTION_POLLACHI", "ROAD_NH83", "ROAD", 3000.0),
            ("JUNCTION_DINDIGUL", "JUNCTION_KARUR", "ROAD_NH44_NB", "ROAD", 3400.0),
            ("JUNCTION_DINDIGUL", "JUNCTION_MADURAI", "ROAD_NH44_SB", "ROAD", 3200.0),
            ("JUNCTION_MADURAI", "JUNCTION_DINDIGUL", "ROAD_NH44_NB", "ROAD", 3600.0),
            ("JUNCTION_MADURAI", "CFS_MADURAI_INLAND", "ROAD_0", "ROAD", 2800.0),
            ("CFS_MADURAI_INLAND", "JUNCTION_DINDIGUL", "ROAD_NH44_NB", "ROAD", 3200.0),
            ("CFS_TUTICORIN_BOND", "JUNCTION_MADURAI", "ROAD_NH38_NB", "ROAD", 2800.0),
            ("CFS_TUTICORIN_BOND", "JUNCTION_TIRUNELVELI", "ROAD_0", "ROAD", 2800.0),
            ("JUNCTION_TIRUNELVELI", "JUNCTION_MADURAI", "ROAD_NH44_NB", "ROAD", 3000.0),
            # West Corridor: Cochin -> Thrissur -> Palakkad -> Walayar -> Coimbatore (Eliminating Irugur Bottleneck)
            ("CFS_COCHIN_VALLARPADAM", "JUNCTION_THRISSUR", "ROAD_0", "ROAD", 3200.0),
            ("CFS_COCHIN_VALLARPADAM", "ICD_IRUGUR", "RAIL_CONCOR", "RAIL", 2000.0),
            ("JUNCTION_THRISSUR", "JUNCTION_PALAKKAD", "ROAD_NH544", "ROAD", 3800.0),
            ("JUNCTION_PALAKKAD", "PLANT_PALAKKAD_COMPONENTS", "ROAD_0", "ROAD", 2200.0),
            ("JUNCTION_PALAKKAD", "CFS_PALAKKAD_FREIGHT", "ROAD_0", "ROAD", 2800.0),
            ("JUNCTION_PALAKKAD", "JUNCTION_WALAYAR", "ROAD_NH544", "ROAD", 3800.0),
            ("CFS_PALAKKAD_FREIGHT", "PLANT_PALAKKAD_COMPONENTS", "ROAD_FEED", "ROAD", 2000.0),
            ("CFS_PALAKKAD_FREIGHT", "JUNCTION_WALAYAR", "ROAD_0", "ROAD", 2800.0),
            ("JUNCTION_WALAYAR", "PLANT_COIMBATORE", "ROAD_BYPASS", "ROAD", 2600.0),
            ("JUNCTION_WALAYAR", "PLANT_KINATHUKADAVU", "ROAD_0", "ROAD", 2000.0),
            ("JUNCTION_WALAYAR", "CFS_COIMBATORE_NEELAMBUR", "ROAD_BYPASS", "ROAD", 3000.0),
            ("JUNCTION_POLLACHI", "PLANT_KINATHUKADAVU", "ROAD_0", "ROAD", 2200.0),
            ("JUNCTION_POLLACHI", "PLANT_COIMBATORE", "ROAD_SOUTH", "ROAD", 2200.0),
            ("ICD_IRUGUR", "CFS_COIMBATORE_NEELAMBUR", "ROAD_0", "ROAD", 2800.0),
            ("ICD_IRUGUR", "JUNCTION_AVINASHI", "ROAD_NH544", "ROAD", 3000.0),
            ("CFS_COIMBATORE_NEELAMBUR", "PLANT_COIMBATORE", "ROAD_DIRECT", "ROAD", 2600.0),
            ("CFS_COIMBATORE_NEELAMBUR", "JUNCTION_AVINASHI", "ROAD_NH544", "ROAD", 3200.0),
            ("JUNCTION_AVINASHI", "PLANT_COIMBATORE", "ROAD_EAST_BYPASS", "ROAD", 2400.0),
            ("JUNCTION_AVINASHI", "CFS_COIMBATORE_NEELAMBUR", "ROAD_NH544_WB", "ROAD", 3000.0),
            ("JUNCTION_AVINASHI", "JUNCTION_ERODE", "ROAD_NH544", "ROAD", 3600.0),
            ("JUNCTION_ERODE", "JUNCTION_AVINASHI", "ROAD_NH544_WB", "ROAD", 3600.0),
            ("JUNCTION_ERODE", "ICD_SALEM", "ROAD_NH544", "ROAD", 3400.0),
            ("JUNCTION_ERODE", "CFS_SALEM_LOGISTICS", "ROAD_0", "ROAD", 3000.0),
            # Salem / Dharmapuri / Krishnagiri / Hosur Central Spine
            ("ICD_SALEM", "PLANT_SALEM_STEEL", "ROAD_0", "ROAD", 2200.0),
            ("ICD_SALEM", "CFS_SALEM_LOGISTICS", "ROAD_0", "ROAD", 2800.0),
            ("ICD_SALEM", "JUNCTION_SALEM_BYPASS", "ROAD_0", "ROAD", 3200.0),
            ("ICD_SALEM", "ICD_IRUGUR", "RAIL_CONCOR", "RAIL", 2000.0),
            ("ICD_SALEM", "ICD_HOSUR", "RAIL_CONCOR", "RAIL", 2200.0),
            ("CFS_SALEM_LOGISTICS", "PLANT_SALEM_STEEL", "ROAD_0", "ROAD", 2000.0),
            ("CFS_SALEM_LOGISTICS", "JUNCTION_SALEM_BYPASS", "ROAD_0", "ROAD", 3200.0),
            ("CFS_SALEM_LOGISTICS", "JUNCTION_ERODE", "ROAD_NH544_WB", "ROAD", 3200.0),
            ("JUNCTION_SALEM_BYPASS", "JUNCTION_DHARMAPURI", "ROAD_NH44", "ROAD", 4200.0),
            ("JUNCTION_SALEM_BYPASS", "JUNCTION_ERODE", "ROAD_NH544_WB", "ROAD", 3600.0),
            ("JUNCTION_SALEM_BYPASS", "JUNCTION_ULUNDURPET", "ROAD_NH79_EB", "ROAD", 3200.0),
            ("JUNCTION_DHARMAPURI", "JUNCTION_KRISHNAGIRI", "ROAD_NH44_NB", "ROAD", 4200.0),
            ("JUNCTION_DHARMAPURI", "JUNCTION_SALEM_BYPASS", "ROAD_NH44_SB", "ROAD", 4000.0),
            # NH48 / Palar Valley (Chennai <-> Ranipet <-> Walajapet <-> Vellore <-> Ambur <-> Krishnagiri)
            ("JUNCTION_RANIPET", "JUNCTION_WALAJAPET", "ROAD_LOCAL", "ROAD", 4500.0),
            ("JUNCTION_RANIPET", "PLANT_CHEYYAR", "ROAD_0", "ROAD", 2000.0),
            ("JUNCTION_WALAJAPET", "JUNCTION_VELLORE", "ROAD_NH48", "ROAD", 4500.0),
            ("JUNCTION_WALAJAPET", "JUNCTION_RANIPET", "ROAD_NH48_EB", "ROAD", 4500.0),
            ("JUNCTION_WALAJAPET", "JUNCTION_CHITTOOR", "ROAD_NH40", "ROAD", 3800.0),
            ("JUNCTION_CHITTOOR", "PLANT_CHITTOOR_AUTO", "ROAD_0", "ROAD", 2200.0),
            ("JUNCTION_CHITTOOR", "PLANT_SRICITY", "ROAD_AP_BYPASS", "ROAD", 2400.0),
            ("JUNCTION_CHITTOOR", "JUNCTION_MULBAGAL", "ROAD_NH69", "ROAD", 3600.0),
            ("JUNCTION_CHITTOOR", "JUNCTION_VELLORE", "ROAD_LOCAL", "ROAD", 3400.0),
            ("JUNCTION_CHITTOOR", "JUNCTION_WALAJAPET", "ROAD_NH40_SB", "ROAD", 3600.0),
            ("JUNCTION_VELLORE", "PLANT_CHITTOOR_AUTO", "ROAD_0", "ROAD", 2000.0),
            ("JUNCTION_VELLORE", "JUNCTION_AMBUR", "ROAD_NH48", "ROAD", 4500.0),
            ("JUNCTION_AMBUR", "JUNCTION_KRISHNAGIRI", "ROAD_NH48", "ROAD", 4500.0),
            ("JUNCTION_AMBUR", "JUNCTION_VELLORE", "ROAD_NH48_EB", "ROAD", 4500.0),
            ("JUNCTION_KRISHNAGIRI", "PLANT_KRISHNAGIRI_TIER1", "ROAD_0", "ROAD", 2400.0),
            ("JUNCTION_KRISHNAGIRI", "JUNCTION_AMBUR", "ROAD_NH48_EB", "ROAD", 4500.0),
            ("JUNCTION_KRISHNAGIRI", "JUNCTION_DHARMAPURI", "ROAD_NH44_SB", "ROAD", 4200.0),
            ("JUNCTION_KRISHNAGIRI", "JUNCTION_KOLAR", "ROAD_SPUR", "ROAD", 3400.0),
            ("JUNCTION_KRISHNAGIRI", "ICD_HOSUR", "ROAD_NH44", "ROAD", 3800.0),
            ("JUNCTION_KRISHNAGIRI", "CFS_HOSUR_LOGISTICS", "ROAD_NH44", "ROAD", 3800.0),
            # Hosur & Bengaluru Tier-1 Cluster (Eliminating Bidadi Single-Point Bottleneck)
            ("ICD_HOSUR", "PLANT_HOSUR", "ROAD_0", "ROAD", 2800.0),
            ("ICD_HOSUR", "CFS_HOSUR_LOGISTICS", "ROAD_0", "ROAD", 3200.0),
            ("ICD_HOSUR", "ICD_WHITEFIELD", "RAIL_CONCOR", "RAIL", 2400.0),
            ("ICD_HOSUR", "JUNCTION_ATTIBELE", "ROAD_NH44", "ROAD", 3600.0),
            ("CFS_HOSUR_LOGISTICS", "PLANT_HOSUR", "ROAD_0", "ROAD", 2800.0),
            ("CFS_HOSUR_LOGISTICS", "PLANT_KRISHNAGIRI_TIER1", "ROAD_SPUR", "ROAD", 2200.0),
            ("CFS_HOSUR_LOGISTICS", "JUNCTION_ATTIBELE", "ROAD_NH44", "ROAD", 3800.0),
            ("JUNCTION_ATTIBELE", "PLANT_BOMMASANDRA", "ROAD_0", "ROAD", 2400.0),
            ("JUNCTION_ATTIBELE", "CFS_BOMMASANDRA", "ROAD_0", "ROAD", 3200.0),
            ("JUNCTION_ATTIBELE", "JUNCTION_ELECTRONIC_CITY", "ROAD_NH44", "ROAD", 4500.0),
            ("JUNCTION_ATTIBELE", "JUNCTION_HOSKOTE", "ROAD_STRR", "ROAD", 3600.0),
            ("CFS_BOMMASANDRA", "PLANT_BOMMASANDRA", "ROAD_0", "ROAD", 2400.0),
            ("CFS_BOMMASANDRA", "PLANT_HAROHALLI", "ROAD_STRR", "ROAD", 2200.0),
            ("CFS_BOMMASANDRA", "JUNCTION_ELECTRONIC_CITY", "ROAD_0", "ROAD", 3200.0),
            ("JUNCTION_ELECTRONIC_CITY", "PLANT_BIDADI", "ROAD_NICE", "ROAD", 2800.0),
            ("JUNCTION_ELECTRONIC_CITY", "PLANT_HAROHALLI", "ROAD_SOUTH", "ROAD", 2200.0),
            ("JUNCTION_ELECTRONIC_CITY", "CFS_WHITEFIELD", "ROAD_ORR", "ROAD", 3200.0),
            ("JUNCTION_MULBAGAL", "PLANT_VEMAGAL", "ROAD_NH75", "ROAD", 2200.0),
            ("JUNCTION_MULBAGAL", "JUNCTION_KOLAR", "ROAD_NH75", "ROAD", 4000.0),
            ("JUNCTION_KOLAR", "PLANT_NARASAPURA", "ROAD_0", "ROAD", 2400.0),
            ("JUNCTION_KOLAR", "PLANT_VEMAGAL", "ROAD_0", "ROAD", 2200.0),
            ("JUNCTION_KOLAR", "JUNCTION_HOSKOTE", "ROAD_NH75", "ROAD", 4200.0),
            ("JUNCTION_HOSKOTE", "CFS_WHITEFIELD", "ROAD_0", "ROAD", 3400.0),
            ("JUNCTION_HOSKOTE", "ICD_WHITEFIELD", "ROAD_0", "ROAD", 3400.0),
            ("JUNCTION_HOSKOTE", "PLANT_NARASAPURA", "ROAD_EB", "ROAD", 2400.0),
            ("JUNCTION_HOSKOTE", "JUNCTION_NELAMANGALA", "ROAD_STRR", "ROAD", 3800.0),
            ("CFS_WHITEFIELD", "PLANT_PEENYA", "ROAD_ORR", "ROAD", 2400.0),
            ("CFS_WHITEFIELD", "CFS_BOMMASANDRA", "ROAD_0", "ROAD", 2800.0),
            # West Coast NMPT -> Hassan -> Nelamangala / Kunigal -> Mysuru -> Bidadi
            ("CFS_MANGALORE_PANAMBUR", "JUNCTION_HASSAN", "ROAD_NH75", "ROAD", 2800.0),
            ("JUNCTION_HASSAN", "JUNCTION_KUNIGAL", "ROAD_NH75", "ROAD", 3400.0),
            ("JUNCTION_HASSAN", "JUNCTION_MYSURU_RING", "ROAD_SOUTH", "ROAD", 3000.0),
            ("JUNCTION_HASSAN", "PLANT_TUMAKURU", "ROAD_SPUR", "ROAD", 2200.0),
            ("JUNCTION_KUNIGAL", "JUNCTION_NELAMANGALA", "ROAD_NH75", "ROAD", 3600.0),
            ("JUNCTION_KUNIGAL", "JUNCTION_RAMANAGARA", "ROAD_SPUR", "ROAD", 3000.0),
            ("JUNCTION_KUNIGAL", "PLANT_TUMAKURU", "ROAD_NORTH", "ROAD", 2200.0),
            ("JUNCTION_MYSURU_RING", "JUNCTION_MANDYA", "ROAD_NH275", "ROAD", 3200.0),
            ("JUNCTION_MYSURU_RING", "JUNCTION_PALAKKAD", "ROAD_NH766", "ROAD", 2800.0),
            ("JUNCTION_MANDYA", "JUNCTION_RAMANAGARA", "ROAD_NH275", "ROAD", 3400.0),
            ("JUNCTION_MANDYA", "PLANT_HAROHALLI", "ROAD_SOUTH", "ROAD", 2200.0),
            ("JUNCTION_RAMANAGARA", "PLANT_BIDADI", "ROAD_NH275", "ROAD", 2800.0),
            ("JUNCTION_RAMANAGARA", "PLANT_HAROHALLI", "ROAD_STRR", "ROAD", 2200.0),
            ("JUNCTION_NELAMANGALA", "CFS_NELAMANGALA", "ROAD_0", "ROAD", 3400.0),
            ("JUNCTION_NELAMANGALA", "JUNCTION_TUMAKURU_NH48", "ROAD_NH48_NB", "ROAD", 3600.0),
            ("JUNCTION_NELAMANGALA", "PLANT_PEENYA", "ROAD_NH48", "ROAD", 2600.0),
            ("JUNCTION_NELAMANGALA", "PLANT_BIDADI", "ROAD_NICE_WEST", "ROAD", 2600.0),
            ("CFS_NELAMANGALA", "PLANT_PEENYA", "ROAD_0", "ROAD", 2600.0),
            ("CFS_NELAMANGALA", "PLANT_DOBBASPET", "ROAD_NH48", "ROAD", 2200.0),
            ("CFS_NELAMANGALA", "PLANT_TUMAKURU", "ROAD_NH48_FEED", "ROAD", 2200.0),
            ("CFS_NELAMANGALA", "CFS_WHITEFIELD", "ROAD_RING", "ROAD", 3000.0),
            ("JUNCTION_TUMAKURU_NH48", "PLANT_DOBBASPET", "ROAD_0", "ROAD", 2200.0),
            ("JUNCTION_TUMAKURU_NH48", "PLANT_TUMAKURU", "ROAD_0", "ROAD", 2400.0),
            ("JUNCTION_TUMAKURU_NH48", "JUNCTION_NELAMANGALA", "ROAD_NH48_SB", "ROAD", 3600.0),
            ("PLANT_DOBBASPET", "PLANT_TUMAKURU", "ROAD_SPUR", "ROAD", 2000.0),
            ("PLANT_TUMAKURU", "PLANT_DOBBASPET", "ROAD_SPUR", "ROAD", 2000.0),
            # Bidirectional Return Feeder Links Ensuring Full East-West Flexibility
            ("PLANT_SRIPERUMBUDUR", "CFS_ORAGADAM", "ROAD_CROSS", "ROAD", 2400.0),
            ("PLANT_ORAGADAM", "CFS_SRIPERUMBUDUR", "ROAD_CROSS", "ROAD", 2400.0),
            ("ICD_WHITEFIELD", "JUNCTION_HOSKOTE", "ROAD_EB", "ROAD", 3200.0),
            ("ICD_WHITEFIELD", "JUNCTION_ELECTRONIC_CITY", "ROAD_NICE", "ROAD", 3000.0),
            ("ICD_WHITEFIELD", "CFS_NELAMANGALA", "ROAD_RING", "ROAD", 2800.0),
            ("ICD_WHITEFIELD", "PLANT_PEENYA", "ROAD_ORR", "ROAD", 2600.0),
            ("ICD_WHITEFIELD", "PLANT_BOMMASANDRA", "ROAD_0", "ROAD", 2400.0),
            ("ICD_WHITEFIELD", "PLANT_NARASAPURA", "ROAD_NH75", "ROAD", 2400.0),
            ("ICD_WHITEFIELD", "PLANT_VEMAGAL", "ROAD_NH75", "ROAD", 2200.0),
            ("PLANT_HOSUR", "JUNCTION_ATTIBELE", "ROAD_NB", "ROAD", 3200.0),
            ("PLANT_HOSUR", "JUNCTION_KRISHNAGIRI", "ROAD_NH44_EB", "ROAD", 3200.0),
            # Additional Regional Cross-Corridor Freight & Intermodal Links (Zero Single-Point Cuts)
            ("PORT_KAMARAJAR", "ICD_SALEM", "RAIL_SOUTH", "RAIL", 1800.0),
            ("PORT_KATTUPALLI", "CFS_MANALI", "ROAD_COASTAL", "ROAD", 2600.0),
            ("PORT_KATTUPALLI", "CFS_CHENNAI_CENTRAL", "ROAD_BYPASS", "ROAD", 2600.0),
            ("PORT_CHENNAI", "JUNCTION_TIRUVALLUR", "ROAD_NH716", "ROAD", 2800.0),
            ("PORT_KRISHNAPATNAM", "CFS_SULLURPETA", "ROAD_NH16_SB", "ROAD", 3200.0),
            ("PORT_KRISHNAPATNAM", "JUNCTION_NAIDUPETA", "ROAD_SPUR", "ROAD", 3000.0),
            ("PORT_KARAIKAL", "ICD_SALEM", "RAIL_KAVERI", "RAIL", 1800.0),
            ("PORT_KARAIKAL", "JUNCTION_VILLUPURAM", "ROAD_EC", "ROAD", 2200.0),
            ("PORT_VOC", "CFS_MADURAI_INLAND", "ROAD_NH38", "ROAD", 2400.0),
            ("PORT_COCHIN", "CFS_PALAKKAD_FREIGHT", "ROAD_NH544", "ROAD", 2600.0),
            ("PORT_COCHIN", "JUNCTION_MYSURU_RING", "ROAD_HILL", "ROAD", 2000.0),
            ("PORT_NEW_MANGALORE", "JUNCTION_MYSURU_RING", "ROAD_GHAT", "ROAD", 2400.0),
            ("PORT_NEW_MANGALORE", "CFS_NELAMANGALA", "RAIL_WEST", "RAIL", 1600.0),
            ("ICD_TONDIARPET", "PLANT_AMBATTUR", "ROAD_0", "ROAD", 2400.0),
            ("ICD_TONDIARPET", "PLANT_GUMMIDIPOONDI", "ROAD_0", "ROAD", 2200.0),
            ("ICD_TONDIARPET", "PLANT_THIRUVALLUR", "ROAD_0", "ROAD", 2200.0),
            ("ICD_TONDIARPET", "JUNCTION_CHENGALPATTU", "ROAD_ORR", "ROAD", 2600.0),
            ("ICD_HOSUR", "PLANT_BOMMASANDRA", "ROAD_0", "ROAD", 2400.0),
            ("ICD_HOSUR", "PLANT_BIDADI", "ROAD_NICE", "ROAD", 2400.0),
            ("ICD_HOSUR", "PLANT_KRISHNAGIRI_TIER1", "ROAD_EB", "ROAD", 2400.0),
            ("ICD_HOSUR", "JUNCTION_DHARMAPURI", "ROAD_NH44_SB", "ROAD", 2800.0),
            ("ICD_SALEM", "ICD_WHITEFIELD", "RAIL_CONCOR", "RAIL", 2000.0),
            ("ICD_SALEM", "PLANT_KINATHUKADAVU", "ROAD_SOUTH", "ROAD", 2000.0),
            ("ICD_SALEM", "PLANT_COIMBATORE", "ROAD_NH544", "ROAD", 2400.0),
            ("ICD_SALEM", "JUNCTION_TRICHY", "ROAD_EAST", "ROAD", 2400.0),
            ("ICD_IRUGUR", "PLANT_KINATHUKADAVU", "ROAD_0", "ROAD", 2200.0),
            ("ICD_IRUGUR", "PLANT_PALAKKAD_COMPONENTS", "ROAD_NH544_WB", "ROAD", 2200.0),
            ("ICD_KRISHNAPATNAM_RAIL", "PLANT_NELLORE_TIER1", "ROAD_0", "ROAD", 2400.0),
            ("ICD_KRISHNAPATNAM_RAIL", "PLANT_NAIDUPETA", "ROAD_0", "ROAD", 2200.0),
            ("ICD_KRISHNAPATNAM_RAIL", "PLANT_TADA", "RAIL_SPUR", "RAIL", 2000.0),
            ("ICD_KRISHNAPATNAM_RAIL", "PLANT_SRICITY", "ROAD_SPUR", "ROAD", 2200.0),
            ("CFS_PONNERI", "PLANT_TADA", "ROAD_NH16", "ROAD", 2200.0),
            ("CFS_PONNERI", "PLANT_THIRUVALLUR", "ROAD_SPUR", "ROAD", 2200.0),
            ("CFS_MANALI", "PLANT_MARAIMALAI", "ROAD_BYPASS", "ROAD", 2200.0),
            ("CFS_MANALI", "PLANT_IRUNGATTUKOTTAI", "ROAD_0", "ROAD", 2400.0),
            ("CFS_ENNORE_LOGISTICS", "PLANT_AMBATTUR", "ROAD_0", "ROAD", 2200.0),
            ("CFS_ENNORE_LOGISTICS", "PLANT_GUMMIDIPOONDI", "ROAD_NORTH", "ROAD", 2200.0),
            ("CFS_MINJUR", "PLANT_GUMMIDIPOONDI", "ROAD_NH16", "ROAD", 2200.0),
            ("CFS_MINJUR", "PLANT_SRICITY", "ROAD_BYPASS", "ROAD", 2200.0),
            ("CFS_CHENNAI_CENTRAL", "PLANT_IRUNGATTUKOTTAI", "ROAD_0", "ROAD", 2400.0),
            ("CFS_CHENNAI_CENTRAL", "PLANT_VALLAM_VADAGAL", "ROAD_0", "ROAD", 2200.0),
            ("CFS_CHENNAI_CENTRAL", "PLANT_CHENGALPATTU", "ROAD_0", "ROAD", 2200.0),
            ("CFS_CHENNAI_CENTRAL", "PLANT_THIRUVALLUR", "ROAD_0", "ROAD", 2200.0),
            ("CFS_CHENNAI_CENTRAL", "PLANT_MARAIMALAI", "ROAD_0", "ROAD", 2200.0),
            ("JUNCTION_TAMBARAM", "PLANT_CHENGALPATTU", "ROAD_NH32", "ROAD", 2400.0),
            ("JUNCTION_TAMBARAM", "PLANT_VALLAM_VADAGAL", "ROAD_ORR", "ROAD", 2200.0),
            ("JUNCTION_TAMBARAM", "PLANT_ORAGADAM", "ROAD_0", "ROAD", 2600.0),
            ("JUNCTION_TAMBARAM", "PLANT_SRIPERUMBUDUR", "ROAD_0", "ROAD", 2600.0),
            ("JUNCTION_RANIPET", "PLANT_IRUNGATTUKOTTAI", "ROAD_NH48_EB", "ROAD", 2400.0),
            ("JUNCTION_WALAJAPET", "PLANT_CHEYYAR", "ROAD_0", "ROAD", 2200.0),
            ("JUNCTION_WALAJAPET", "PLANT_ORAGADAM", "ROAD_NH48_EB", "ROAD", 2600.0),
            ("JUNCTION_WALAJAPET", "PLANT_SRIPERUMBUDUR", "ROAD_NH48_EB", "ROAD", 2600.0),
            ("JUNCTION_AMBUR", "PLANT_KRISHNAGIRI_TIER1", "ROAD_NH48", "ROAD", 2200.0),
            ("JUNCTION_AMBUR", "PLANT_SALEM_STEEL", "ROAD_SOUTH", "ROAD", 2000.0),
            ("JUNCTION_CHITTOOR", "PLANT_TIRUPATI_ELECTRONICS", "ROAD_0", "ROAD", 2200.0),
            ("JUNCTION_CHITTOOR", "PLANT_NARASAPURA", "ROAD_NH75", "ROAD", 2200.0),
            ("JUNCTION_MULBAGAL", "PLANT_CHITTOOR_AUTO", "ROAD_EB", "ROAD", 2000.0),
            ("JUNCTION_MULBAGAL", "PLANT_NARASAPURA", "ROAD_NH75", "ROAD", 2400.0),
            ("JUNCTION_ATTIBELE", "PLANT_BIDADI", "ROAD_NICE", "ROAD", 2600.0),
            ("JUNCTION_ATTIBELE", "PLANT_HAROHALLI", "ROAD_STRR", "ROAD", 2200.0),
            ("CFS_MADURAI_INLAND", "JUNCTION_KARUR", "ROAD_NH44_NB", "ROAD", 2600.0),
            ("CFS_COCHIN_VALLARPADAM", "PLANT_PALAKKAD_COMPONENTS", "ROAD_DIRECT", "ROAD", 2200.0),
            ("JUNCTION_THRISSUR", "CFS_PALAKKAD_FREIGHT", "ROAD_NH544", "ROAD", 2600.0),
            ("CFS_COIMBATORE_NEELAMBUR", "PLANT_KINATHUKADAVU", "ROAD_0", "ROAD", 2200.0),
            ("CFS_SALEM_LOGISTICS", "JUNCTION_KRISHNAGIRI", "ROAD_NH44_NB", "ROAD", 2600.0),
            ("CFS_KRISHNAPATNAM", "PLANT_NAIDUPETA", "ROAD_NH16_SB", "ROAD", 2200.0),
            ("CFS_KRISHNAPATNAM", "JUNCTION_RENIGUNTA", "ROAD_NH71", "ROAD", 2600.0),
            # Outbound Market Gateway Links (Connecting Plants & Hubs to Export / National Markets)
            ("JUNCTION_TUMAKURU_NH48", "OUTBOUND_PUNE_MUMBAI_NH48", "ROAD_OUT", "ROAD", 4000.0),
            ("JUNCTION_HOSKOTE", "OUTBOUND_BENGALURU_NORTH_AIR", "ROAD_OUT", "ROAD", 4000.0),
            ("JUNCTION_NELAMANGALA", "OUTBOUND_HYDERABAD_NH44", "ROAD_OUT", "ROAD", 4000.0),
            ("JUNCTION_GUDUR", "OUTBOUND_VIJAYAWADA_NH16", "ROAD_OUT", "ROAD", 4000.0),
            ("JUNCTION_RENIGUNTA", "OUTBOUND_TIRUPATI_GATE", "ROAD_OUT", "ROAD", 3500.0),
            ("CFS_MANGALORE_PANAMBUR", "OUTBOUND_MANGALORE_COAST", "ROAD_OUT", "ROAD", 3500.0),
            ("PORT_COCHIN", "OUTBOUND_COCHIN_EXPORT_GATE", "ROAD_OUT", "ROAD", 3500.0),
            ("PORT_VOC", "OUTBOUND_TUTICORIN_DEEPSEA", "ROAD_OUT", "ROAD", 3000.0),
            ("PORT_CHENNAI", "OUTBOUND_CHENNAI_EXPORT_GATE", "ROAD_OUT", "ROAD", 5000.0),
            ("PLANT_COIMBATORE", "OUTBOUND_COIMBATORE_WEST_GATE", "ROAD_OUT", "ROAD", 3500.0),
        ]
        return specs

    @classmethod
    def calibrate_edges_with_osmnx(
        cls,
        entities_by_id: dict[str, dict[str, Any]],
        links: list[dict[str, Any]],
        place_name: str = "Tamil Nadu, India",
    ) -> tuple[list[dict[str, Any]], bool]:
        """
        Optionally snap corridor road edges against OpenStreetMap highway geometries via OSMnx.
        Returns (calibrated_links, used_live_osmnx). Falls back cleanly if osmnx is unavailable.
        """
        if ox is None:
            return links, False

        road_graph = ox.graph_from_place(place_name, network_type="drive")
        calibrated: list[dict[str, Any]] = []
        for link in links:
            row = dict(link)
            if str(row.get("mode", "ROAD")).upper() == "ROAD":
                src = entities_by_id[row["source"]]
                dst = entities_by_id[row["target"]]
                try:
                    n1 = ox.distance.nearest_nodes(road_graph, src["longitude"], src["latitude"])
                    n2 = ox.distance.nearest_nodes(road_graph, dst["longitude"], dst["latitude"])
                    length_m = ox.shortest_path_length(road_graph, n1, n2, weight="length")
                    if length_m and length_m > 0:
                        dist_km = round(float(length_m) / 1000.0, 2)
                        row["distance_km"] = dist_km
                        row["transit_time_hrs"] = round(max(0.25, dist_km / 52.0), 2)
                except Exception:
                    pass
            calibrated.append(row)
        return calibrated, True

    @classmethod
    def build_v1_payloads(
        cls,
        seeds_dir: Path | None = None,
        use_osmnx: bool = False,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Construct scaled 118-node registry and ~380-edge corridor multigraph JSON payloads."""
        base_dir = seeds_dir or _default_seeds_dir()
        with open(base_dir / "corridor_registry.json", encoding="utf-8") as f:
            v0_reg = json.load(f)
        with open(base_dir / "corridor_graph_v0.json", encoding="utf-8") as f:
            v0_graph = json.load(f)

        entities = list(v0_reg.get("entities", [])) + cls._extra_entities()
        entities_by_id = {e["id"]: e for e in entities}

        # Preserve every valid v0 edge with scaled trunk floor where needed for multi-plant throughput
        links: list[dict[str, Any]] = []
        seen_edge_keys: set[tuple[str, str, str]] = set()
        for raw_link in v0_graph.get("links", []):
            item = dict(raw_link)
            links.append(item)
            seen_edge_keys.add((item["source"], item["target"], item.get("key", "default")))

        for src, dst, key, mode, cap in cls._edge_specs():
            if src not in entities_by_id or dst not in entities_by_id:
                raise KeyError(f"Edge ({src} -> {dst}) references ungrounded entity ID")
            if (src, dst, key) in seen_edge_keys:
                continue
            seen_edge_keys.add((src, dst, key))
            e_src = entities_by_id[src]
            e_dst = entities_by_id[dst]
            raw_dist = _haversine_km(
                e_src["latitude"], e_src["longitude"], e_dst["latitude"], e_dst["longitude"]
            )
            circuity = 1.18 if mode == "RAIL" else 1.24
            dist_km = round(max(4.0, raw_dist * circuity), 1)
            speed_kmh = 42.0 if mode == "RAIL" else 54.0
            dwell_hrs = 0.8 if mode == "RAIL" else 0.35
            transit_hrs = round(max(0.3, (dist_km / speed_kmh) + dwell_hrs), 2)
            rate_per_km = 0.56 if mode == "RAIL" else 1.28
            cost_teu = round(max(20.0, dist_km * rate_per_km + (12.0 if mode == "RAIL" else 18.0)), 1)
            links.append(
                {
                    "source": src,
                    "target": dst,
                    "key": key,
                    "mode": mode,
                    "distance_km": dist_km,
                    "transit_time_hrs": transit_hrs,
                    "capacity_teu_per_day": cap,
                    "base_cost_per_teu": cost_teu,
                    "active": True,
                }
            )

        if use_osmnx:
            links, _ = cls.calibrate_edges_with_osmnx(entities_by_id, links)

        reg_payload = {
            "version": "2.1.0",
            "corridor": "South India Automotive Logistics Corridor (Scaled v1)",
            "entities": entities,
        }
        graph_payload = {
            "directed": True,
            "multigraph": True,
            "graph": {
                "name": "South India Automotive Logistics Corridor Multigraph v1 (100-150 Node Scale)",
                "version": "2.1.0",
                "crs": "EPSG:4326",
            },
            "nodes": [{"id": e["id"]} for e in entities],
            "links": links,
        }
        return reg_payload, graph_payload

    @classmethod
    def write_v1_seeds(
        cls,
        seeds_dir: Path | None = None,
        use_osmnx: bool = False,
    ) -> tuple[Path, Path]:
        """Generate and validate `corridor_registry_v1.json` & `corridor_graph_v1.json` on disk."""
        base_dir = seeds_dir or _default_seeds_dir()
        reg_payload, graph_payload = cls.build_v1_payloads(seeds_dir=base_dir, use_osmnx=use_osmnx)

        reg_path = base_dir / "corridor_registry_v1.json"
        graph_path = base_dir / "corridor_graph_v1.json"
        reg_path.write_text(json.dumps(reg_payload, indent=2) + "\n", encoding="utf-8")
        graph_path.write_text(json.dumps(graph_payload, indent=2) + "\n", encoding="utf-8")

        # Validate immediately through canonical registry and graph store
        reg = CanonicalEntityRegistry.load_from_json(seed_path=reg_path)
        gs = CorridorGraphStore.load_from_json(seed_path=graph_path, registry=reg)
        assert 100 <= len(reg) <= 150, f"Unexpected node count: {len(reg)}"
        assert 300 <= len(gs.get_all_edges()) <= 500, f"Unexpected edge count: {len(gs.get_all_edges())}"
        for plant in reg.get_by_type(EntityType.PLANT):
            assert gs.graph.in_degree(plant.id) >= 2, f"Plant {plant.id} lacks redundant feeders!"

        return reg_path, graph_path


def load_entities_from_config(seed_registry_path: Path | None, network_scale: str) -> CanonicalEntityRegistry:
    """Resolve registry according to PipelineConfig seed path or network scale."""
    from asci.core.registry import get_canonical_registry

    return get_canonical_registry(seed_path=seed_registry_path, network_scale=network_scale)


def load_graph_from_config(
    seed_graph_path: Path | None,
    registry: CanonicalEntityRegistry,
    network_scale: str,
) -> CorridorGraphStore:
    """Resolve CorridorGraphStore according to PipelineConfig seed path or network scale."""
    return CorridorGraphStore.load_from_json(
        seed_path=seed_graph_path,
        registry=registry,
        network_scale=network_scale,
    )
