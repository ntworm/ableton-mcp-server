import sqlite3
import os
import json
import collections
from pathlib import Path
import sys
import multiprocessing

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ableton_mcp_server.groove_intelligence.midi_lossless import parse_smf
from ableton_mcp_server.groove_intelligence.drum_roles import GM_DRUM_ROLE_BY_PITCH
from ableton_mcp_server.groove_intelligence.articulation import resolve_role

CORPUS_ROOT = Path(r"C:\Users\Usuario\Desktop\AUDIO_PRODUCTION\AUDIO\Superior Drummer 3\Toontrack\Midi")
DB_PATH = Path(r"C:\Users\Usuario\AppData\Local\AbletonMCPServer\groove-build-v2\catalog_v2.sqlite")

def process_chunk(rows):
    hist = collections.defaultdict(lambda: collections.Counter())
    cooc = collections.defaultdict(lambda: collections.Counter())
    for rel_path, stratum in rows:
        try:
            file_path = CORPUS_ROOT / rel_path
            data = file_path.read_bytes()
            parsed = parse_smf(data)
            pitches = [(n.pitch, n.start_ticks) for n in parsed.note_events]
            
            for p, _ in pitches:
                hist[stratum][p] += 1
            
            by_tick = collections.defaultdict(list)
            for p, t in pitches:
                by_tick[t].append(p)
                
            for t, group in by_tick.items():
                if len(group) > 1:
                    unique_p = sorted(list(set(group)))
                    for i in range(len(unique_p)):
                        for j in range(i+1, len(unique_p)):
                            cooc[stratum][(unique_p[i], unique_p[j])] += 1
        except Exception:
            pass
    return dict(hist), dict(cooc), len(rows)

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT relative_path, stratum FROM files WHERE status='ok' AND source_digest != '' GROUP BY source_digest ORDER BY source_digest")
    rows = cursor.fetchall()
    
    print(f"Found {len(rows)} distinct files.", flush=True)
    
    num_workers = 8
    chunk_size = 2000
    chunks = [rows[i:i + chunk_size] for i in range(0, len(rows), chunk_size)]
    
    histograms = collections.defaultdict(lambda: collections.Counter())
    cooccurrences = collections.defaultdict(lambda: collections.Counter())
    
    print(f"Processing in {len(chunks)} chunks of size {chunk_size}...", flush=True)
    
    processed = 0
    with multiprocessing.Pool(num_workers) as pool:
        for hist_chunk, cooc_chunk, count in pool.imap_unordered(process_chunk, chunks):
            for stratum, counts in hist_chunk.items():
                histograms[stratum].update(counts)
            for stratum, counts in cooc_chunk.items():
                cooccurrences[stratum].update(counts)
            processed += count
            print(f"Processed {processed}/{len(rows)}", flush=True)
                
    print("Merging results...", flush=True)
    results = {}
    for stratum, counts in histograms.items():
        total_notes = sum(counts.values())
        if total_notes == 0:
            continue
            
        unresolved_before = sum(c for p, c in counts.items() if GM_DRUM_ROLE_BY_PITCH.get(p, "other_percussion") == "other_percussion")
        unresolved_after = sum(c for p, c in counts.items() if resolve_role(stratum, p) == "other_percussion")
        
        coocc_list = [{"pitches": [k[0], k[1]], "count": v} for k, v in cooccurrences[stratum].most_common(50)]
        
        results[stratum] = {
            "total_notes": total_notes,
            "unresolved_notes": unresolved_before,
            "unresolved_share": unresolved_before / total_notes if total_notes > 0 else 0,
            "unresolved_notes_after": unresolved_after,
            "unresolved_share_after": unresolved_after / total_notes if total_notes > 0 else 0,
            "pitch_histogram": dict(counts),
            "co_occurrence_top50": coocc_list
        }
        
    with open("scripts/measurement_output.json", "w") as f:
        json.dump(results, f, indent=2, sort_keys=True)
        
    print("Done", flush=True)

if __name__ == '__main__':
    multiprocessing.freeze_support()
    main()
