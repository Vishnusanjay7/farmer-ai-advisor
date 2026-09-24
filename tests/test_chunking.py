from backend.app.services.chunking_service import AgronomicChunker


def test_chunk_creation_and_ordering():
    chunker = AgronomicChunker(max_tokens=20, overlap_tokens=5)
    text = """# Paddy IPM\n\nFirst paragraph about stem borer monitoring with pheromone traps.\n\nSecond paragraph detailing biological control with Trichogramma japonicum parasitoids.\n\nThird paragraph covering chemical threshold limits."""
    chunks = chunker.chunk_document(text, base_metadata={"crop_name": "Paddy", "topic": "IPM"})

    assert len(chunks) >= 2
    # Verify sequential ordering
    for idx, chunk in enumerate(chunks):
        assert chunk.chunk_index == idx
        assert chunk.crop_name == "Paddy"
        assert chunk.token_count > 0
        assert len(chunk.content_hash) == 64


def test_paragraph_and_section_boundary_preservation():
    chunker = AgronomicChunker(max_tokens=400)
    text = """## Section 1: Yellow Rust in Wheat\nYellow rust appears as linear stripes on leaves.\n\n## Section 2: Irrigation\nCrown root initiation is critical."""
    chunks = chunker.chunk_document(text, base_metadata={"crop_name": "Wheat"})

    assert len(chunks) == 2
    assert "Yellow Rust" in chunks[0].content
    assert "Crown root initiation" in chunks[1].content
    assert chunks[0].metadata.get("section_heading") == "Section 1: Yellow Rust in Wheat"


def test_metadata_preservation():
    chunker = AgronomicChunker()
    meta = {
        "crop_name": "Millets",
        "state": "Karnataka",
        "season": "Kharif",
        "growth_stage": "Vegetative",
        "topic": "Blast Disease",
    }
    chunks = chunker.chunk_document("Sample agronomic advice for finger millet blast.", base_metadata=meta)
    assert len(chunks) == 1
    assert chunks[0].crop_name == "Millets"
    assert chunks[0].state == "Karnataka"
    assert chunks[0].season == "Kharif"
    assert chunks[0].topic == "Blast Disease"
