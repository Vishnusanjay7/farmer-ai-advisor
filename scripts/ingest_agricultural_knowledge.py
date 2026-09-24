import os
import sys
import hashlib
import time
from datetime import date, datetime, timezone
from typing import List, Dict, Any, Optional

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Load .env.staging if present
staging_env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env.staging"))
if os.path.exists(staging_env_path):
    from dotenv import load_dotenv
    load_dotenv(staging_env_path)

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.db.session import SessionLocal
from backend.app.models.models import SourceDocument, KnowledgeChunk, SyncLog
from backend.app.services.chunking_service import AgronomicChunker
from backend.app.providers.embedding_provider import get_embedding_provider
import asyncio


# ==============================================================================
# AUTHORITATIVE SOURCE REGISTRY
# Only authoritative sources: ICAR, SAUs, State Agriculture Departments, KVKs
# ==============================================================================
AUTHORITATIVE_SOURCE_REGISTRY: List[Dict[str, Any]] = [
    {
        "source_name": "ICAR-IIRR Rice Integrated Pest Management 2024",
        "title": "Integrated Pest & Disease Management for Rice (Paddy) in India",
        "source_type": "ICAR",
        "issuing_authority": "ICAR - Indian Institute of Rice Research (IIRR), Hyderabad",
        "state_applicability": "All-India",
        "agro_climatic_zone": "Tropical & Sub-tropical Wetland Rice Ecosystems",
        "official_document_url": "https://icar-iirr.org/advisory/pop_rice_ipm_2024.pdf",
        "publication_year": 2024,
        "version": "2024.1",
        "source_date": date(2024, 6, 15),
        "language": "en",
        "crop_name": "Paddy",
        "season": "Kharif",
        "text_content": """
# Integrated Pest and Disease Management in Rice (Paddy)

## Yellow Stem Borer (Scirpophaga incertulas) Management
The Yellow Stem Borer causes dead hearts at the vegetative stage and white ears at the heading stage.

### Monitoring and Cultural Control:
- Install sex pheromone traps with 5 mg lures @ 4-5 traps per acre at 20 days after transplanting (DAT).
- Collect and destroy egg masses deposited near leaf tips.
- Avoid excessive and delayed nitrogenous fertilizer applications which increase stem borer susceptibility.

### Biological Control:
- Release egg parasitoid Trichogramma japonicum @ 20,000 to 40,000 adults per acre, 3 to 4 times starting from 25-30 DAT at 10-day intervals.
- Conserve natural spider populations (Lycosa pseudoannulata) by avoiding early-season broad-spectrum pesticide sprays.

### Chemical Intervention (Only when Economic Threshold Level of 5% dead hearts or 1 egg mass/sq.m is crossed):
- Cartap Hydrochloride 50% SP @ 400 g in 200 liters of water per acre, OR
- Chlorantraniliprole 18.5% SC @ 60 ml in 200 liters of water per acre.
Pre-harvest Interval (PHI): Ensure 21 days between spraying and harvesting. Use protective masks and gloves during spraying.

## Brown Planthopper (Nilaparvata lugens) Management
BPH causes hopper burn in circular patches due to sap sucking at the base of tillers.

### Cultural and Agronomic Management:
- Form alleys (walking paths) of 30 cm after every 2 meters of planting to provide aeration and sunlight to the base of the plant.
- Drain standing water from the field for 3-4 days at the first sign of hopper infestation (alternate wetting and drying).
- Avoid indiscriminate use of synthetic pyrethroids which induce resurgence of BPH populations.

### Chemical Control at ETL (10-15 hoppers per hill):
- Triflumezopyrim 10% SC @ 94 ml per acre, OR
- Pymetrozine 50% WG @ 120 g per acre. Direct spray nozzle strictly to the base of the plant canopy.
"""
    },
    {
        "source_name": "IARI Wheat Package of Practices 2024",
        "title": "Wheat Production Technology, Nutrient Schedule & Rust Disease Prevention",
        "source_type": "ICAR",
        "issuing_authority": "ICAR - Indian Agricultural Research Institute (IARI / Pusa), New Delhi",
        "state_applicability": "North-Western & Central Plains Zones",
        "agro_climatic_zone": "Indo-Gangetic Alluvial & Semi-Arid Plains",
        "official_document_url": "https://iari.res.in/technologies/wheat_production_guide_2024.pdf",
        "publication_year": 2024,
        "version": "2024.2",
        "source_date": date(2024, 10, 1),
        "language": "en",
        "crop_name": "Wheat",
        "season": "Rabi",
        "text_content": """
# Wheat Production and Health Management

## Optimum Sowing Window and Seed Rate
- Timely sown irrigated wheat: November 5 to November 25 is the ideal window for maximum yield potential.
- Seed rate: 40 kg per acre for timely sowing; increase to 50 kg per acre for late sowing (after December 10).
- Seed Treatment: Treat seeds with Trichoderma harzianum @ 4 g/kg seed or Carboxin 37.5% + Thiram 37.5% DS @ 2 g/kg seed to prevent loose smut and seedling blight.

## Critical Irrigation Stages
Wheat requires 4 to 6 irrigations depending on soil texture:
1. Crown Root Initiation (CRI) stage: 20-25 days after sowing (Most critical - never delay this irrigation).
2. Tillering stage: 40-45 days after sowing.
3. Jointing stage: 60-65 days after sowing.
4. Flowering stage: 80-85 days after sowing.
5. Milking stage: 100-105 days after sowing.

## Yellow Rust (Puccinia striiformis) Prevention
- Symptoms: Linear yellow stripes of powdery pustules on leaves during cold, humid weather.
- Monitoring: Inspect fields regularly from January onwards, especially along water channels and shaded tree lines.
- Chemical Management at initial detection: Spray Propiconazole 25% EC @ 200 ml in 200 liters of water per acre. Repeat after 15 days only if disease persists.
"""
    },
    {
        "source_name": "ANGRAU Chili Integrated Pest Protocol",
        "title": "Scientific Management of Thrips, Mites and Murda Complex in Chili",
        "source_type": "SAU_POP",
        "issuing_authority": "Acharya N.G. Ranga Agricultural University (ANGRAU), Andhra Pradesh",
        "state_applicability": "Andhra Pradesh & Telangana",
        "agro_climatic_zone": "Southern Semi-Arid Peninsular Zone",
        "official_document_url": "https://angrau.ac.in/advisories/chili_thrips_murda_protocol.pdf",
        "publication_year": 2024,
        "version": "2024.3",
        "source_date": date(2024, 8, 20),
        "language": "en",
        "crop_name": "Chili",
        "season": "Kharif-Rabi",
        "text_content": """
# Chili Pest Management and Murda (Leaf Curl) Complex

## Chili Thrips (Scirtothrips dorsalis) and Invasive Black Thrips (Thrips parvispinus)
- Symptoms: Leaves curl upward with boat-shaped appearance; necrotic silver-brown patches on under-surface; flower and fruit drop.

### Preventive Cultural Practices:
- Install blue sticky traps @ 30 to 40 per acre at crop canopy level for early detection and mass trapping.
- Grow 2-3 border rows of sorghum, maize, or pearl millet as barrier crops to restrict thrips movement.
- Maintain adequate field moisture; avoid drought stress as dry conditions accelerate thrips proliferation.

### Botanical and Bio-control:
- Neem seed kernel extract (NSKE) 5% or Cold-pressed Neem Oil 10,000 ppm @ 2 ml per liter of water at first sign of infestation.
- Entomopathogenic fungi Lecanicillium lecanii @ 5 g per liter of water during humid evening hours.

### Recommended Chemical Treatment:
- Spinetoram 11.7% SC @ 160 ml per acre in 200 L water, OR
- Fipronil 5% SC @ 400 ml per acre. Rotate chemical groups to prevent resistance development.
"""
    },
    {
        "source_name": "CICR Cotton Pest Guidelines",
        "title": "Integrated Management of Pink Bollworm and Sucking Pests in Cotton",
        "source_type": "ICAR",
        "issuing_authority": "ICAR - Central Institute for Cotton Research (CICR), Nagpur",
        "state_applicability": "Central & Southern Cotton Growing Zones",
        "agro_climatic_zone": "Black Soil Deciduous Semi-Arid Zone",
        "official_document_url": "https://cicr.org.in/advisories/cotton_ipm_guidelines_2024.pdf",
        "publication_year": 2024,
        "version": "2024.1",
        "source_date": date(2024, 7, 10),
        "language": "en",
        "crop_name": "Cotton",
        "season": "Kharif",
        "text_content": """
# Cotton Pest Management Guidelines

## Pink Bollworm (Pectinophora gossypiella)
- Symptoms: Rosetted flowers, small exit holes on developing bolls with stained lint and damaged seeds.

### Management Schedule:
- 45 days after sowing: Install 2 pheromone traps per acre for pest surveillance.
- ETL: Continuous catch of 8 moths per trap per night for 3 consecutive days, OR 10% damaged green bolls with live larvae.
- Light traps: Install 1 solar light trap per 3 acres to catch adult moths between 7:00 PM and 10:00 PM.
- Biological: Release Trichogrammatoidea bactrae @ 60,000 per acre at weekly intervals starting from flowering.
- Chemical (strictly when ETL crossed): Chlorpyrifos 20% EC @ 500 ml/acre or Profenofos 50% EC @ 400 ml/acre. Avoid early application of synthetic pyrethroids.
"""
    },
    {
        "source_name": "PAU Oilseeds & Mustard Guide",
        "title": "Nutrient, Irrigation and Aphid Management for Raya (Mustard)",
        "source_type": "SAU_POP",
        "issuing_authority": "Punjab Agricultural University (PAU), Ludhiana",
        "state_applicability": "Punjab, Haryana & Western UP",
        "agro_climatic_zone": "Trans-Gangetic Plains",
        "official_document_url": "https://pau.edu/pop/oilseeds_mustard_2024.pdf",
        "publication_year": 2024,
        "version": "2024.2",
        "source_date": date(2024, 9, 25),
        "language": "en",
        "crop_name": "Mustard",
        "season": "Rabi",
        "text_content": """
# Mustard (Raya) Production Technology

## Nutrient Management:
- Balanced fertilization: 40 kg Nitrogen (N), 12 kg Phosphorus (P2O5), and 10 kg Sulphur (S) per acre for irrigated raya.
- Apply half Nitrogen and all Phosphorus and Sulphur at sowing time; apply remaining Nitrogen with first irrigation at 30 days.
- Sulphur deficiency leads to cupped young leaves with yellowing; gypsum @ 100 kg/acre or bentonite sulphur @ 10 kg/acre is recommended.

## Mustard Aphid (Lipaphis erysimi) Control:
- Peak occurrence: January to February when cloudy and humid conditions prevail.
- ETL: 10-15% plants showing aphid colonies on top 10 cm central shoot, or 1.5 cm aphid colony length per shoot.
- Conservation: Ladybird beetles (Coccinella septempunctata) and hoverfly maggots are active predators; avoid spraying if predator-prey ratio exceeds 1:50.
- Safe Spray: Thiamethoxam 25% WG @ 40 g/acre or Dimethoate 30% EC @ 250 ml/acre. Spray during afternoon hours to protect honeybee pollinators.
"""
    },
    {
        "source_name": "UAS Bangalore Millets Package of Practices",
        "title": "Finger Millet (Ragi) Production & Blast Disease Management for Rainfed Areas",
        "source_type": "SAU_POP",
        "issuing_authority": "University of Agricultural Sciences (UAS), Bangalore",
        "state_applicability": "Karnataka & Tamil Nadu",
        "agro_climatic_zone": "Southern Dry & Semi-Arid Plateau",
        "official_document_url": "https://uasbangalore.edu.in/pop/millets_ragi_guide_2024.pdf",
        "publication_year": 2024,
        "version": "2024.1",
        "source_date": date(2024, 6, 1),
        "language": "en",
        "crop_name": "Millets",
        "season": "Kharif",
        "text_content": """
# Finger Millet (Ragi) Rainfed Cultivation

## Sowing and Spacing:
- Optimum sowing time: July 15 to August 15 for rainfed kharif.
- Spacing: 30 cm between rows and 10 cm between plants.
- Intercropping: Finger millet + Redgram (8:2 or 4:2 ratio) provides climate resilience and stabilizes net farm income.

## Finger Millet Blast (Magnaporthe grisea):
- Symptoms: Spindle-shaped lesions with ash-grey centers on leaves; neck blast and finger blast prevent grain filling.
- Cultural: Seed treatment with Pseudomonas fluorescens @ 10 g/kg seed or Carbendazim @ 2 g/kg seed.
- Management: Spray Tricyclazole 75% WP @ 120 g per acre in 200 L water at ear emergence stage if neck blast symptoms appear.
"""
    }
]


async def run_ingestion_pipeline():
    """
    Executes the deterministic agricultural knowledge ingestion pipeline.
    Ensures full idempotency and logs execution into sync_logs.
    """
    start_time = time.time()
    db = SessionLocal()
    chunker = AgronomicChunker(max_tokens=400, overlap_tokens=50)
    embedding_provider = get_embedding_provider()

    records_processed = 0
    records_inserted = 0
    records_updated = 0
    records_failed = 0
    status = "SUCCESS"
    error_summary = None

    try:
        logger.info(f"Starting Knowledge Ingestion with {len(AUTHORITATIVE_SOURCE_REGISTRY)} registered sources.")

        for item in AUTHORITATIVE_SOURCE_REGISTRY:
            records_processed += 1
            raw_text = item["text_content"].strip()
            # Deterministic hash of source content
            content_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

            # 1. Upsert SourceDocument by content_hash (idempotency)
            source_doc = db.query(SourceDocument).filter(SourceDocument.content_hash == content_hash).first()
            if not source_doc:
                source_doc = SourceDocument(
                    title=item["title"],
                    source_name=item["source_name"],
                    source_type=item["source_type"],
                    issuing_authority=item["issuing_authority"],
                    state_applicability=item.get("state_applicability", "All-India"),
                    agro_climatic_zone=item.get("agro_climatic_zone"),
                    official_document_url=item.get("official_document_url"),
                    publication_year=item.get("publication_year"),
                    version=item.get("version"),
                    verified_by_expert=True,
                    source_date=item.get("source_date"),
                    content_hash=content_hash,
                    language=item.get("language", "en"),
                    doc_metadata={"crop_name": item.get("crop_name"), "season": item.get("season")},
                )
                db.add(source_doc)
                db.commit()
                db.refresh(source_doc)
                records_inserted += 1
                logger.info(f"Created new source document: '{source_doc.title}' (ID: {source_doc.id})")
            else:
                logger.info(f"Source document already exists (idempotent skip): '{source_doc.title}'")

            # 2. Chunk the text
            chunks = chunker.chunk_document(
                document_text=raw_text,
                base_metadata={
                    "crop_name": item.get("crop_name"),
                    "season": item.get("season"),
                    "state": item.get("state_applicability"),
                    "source_name": item.get("source_name"),
                }
            )

            # 3. Embed and store chunks idempotently
            for chunk in chunks:
                existing_chunk = (
                    db.query(KnowledgeChunk)
                    .filter(
                        KnowledgeChunk.document_id == source_doc.id,
                        KnowledgeChunk.content_hash == chunk.content_hash,
                    )
                    .first()
                )

                if existing_chunk:
                    # Update metadata if needed
                    existing_chunk.chunk_index = chunk.chunk_index
                    existing_chunk.updated_at = datetime.now(timezone.utc)
                    records_updated += 1
                else:
                    # Generate embedding vector (768 dimensions)
                    vector = await embedding_provider.generate_embedding(chunk.content)
                    new_chunk = KnowledgeChunk(
                        document_id=source_doc.id,
                        chunk_index=chunk.chunk_index,
                        crop_name=chunk.crop_name[:100] if chunk.crop_name else None,
                        state=chunk.state[:50] if chunk.state else None,
                        language=item.get("language", "en"),
                        season=chunk.season[:30] if chunk.season else None,
                        growth_stage=chunk.growth_stage[:50] if chunk.growth_stage else None,
                        topic=chunk.topic[:100] if chunk.topic else None,
                        content=chunk.content,
                        content_hash=chunk.content_hash,
                        token_count=chunk.token_count,
                        chunk_metadata=chunk.metadata,
                        embedding=vector,
                    )
                    db.add(new_chunk)
                    records_inserted += 1

            db.commit()

        logger.info("Knowledge Ingestion completed successfully.")

    except Exception as exc:
        db.rollback()
        status = "FAILED"
        records_failed = records_processed
        error_summary = str(exc)
        logger.error(f"Knowledge Ingestion failed: {exc}", exc_info=True)

    finally:
        execution_time = round(time.time() - start_time, 2)
        # Record Ingestion Audit Log
        sync_log = SyncLog(
            sync_source="ICAR_POP_INGEST",
            status=status,
            records_processed=records_processed,
            records_inserted=records_inserted,
            records_updated=records_updated,
            error_message=error_summary,
            execution_time_seconds=execution_time,
        )
        db.add(sync_log)
        db.commit()
        db.close()
        logger.info(f"Audit log created: status={status}, processed={records_processed}, time={execution_time}s")


if __name__ == "__main__":
    if settings.ENVIRONMENT != "staging":
        print(f"FATAL: ingest_agricultural_knowledge.py requires explicit ENVIRONMENT=staging. Current: '{settings.ENVIRONMENT}'. Aborting.")
        sys.exit(1)

    if not settings.DATABASE_URL or "sqlite" in settings.DATABASE_URL.lower():
        print("FATAL: ingest_agricultural_knowledge.py requires a valid PostgreSQL DATABASE_URL. SQLite is strictly rejected.")
        sys.exit(1)

    if not settings.GEMINI_API_KEY:
        print("FATAL: GEMINI_API_KEY is required for knowledge embedding generation in staging.")
        sys.exit(1)

    asyncio.run(run_ingestion_pipeline())
