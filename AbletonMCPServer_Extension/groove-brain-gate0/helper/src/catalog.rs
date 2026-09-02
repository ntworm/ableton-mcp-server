//! The exported seed, held in memory and queried by exact facet match.
//!
//! This is deliberately not the ranker. The Python `groove_search` scores,
//! normalises aliases and pages with cursors; reproducing that here would mean
//! maintaining it twice. Exact matching answers the question Gate 1 asks, and
//! the plan says so out loud rather than implying parity.

use serde::Deserialize;
use std::collections::HashMap;
use std::fs;
use std::path::Path;

pub const EXPORT_SCHEMA: &str = "groove.export.v1";

/// One note as the export writes it: pitch, start tick, duration in ticks, velocity.
pub type ExportedNote = [i64; 4];

#[derive(Debug, Deserialize, Clone)]
pub struct Groove {
    pub id: String,
    pub genre: Vec<String>,
    pub bpm: Vec<String>,
    pub kit: Vec<String>,
    pub bars: u32,
    pub meter: String,
    pub ppq: u32,
    pub notes: Vec<ExportedNote>,
}

#[derive(Debug, Deserialize)]
struct Export {
    schema: String,
    grooves: Vec<Groove>,
}

#[derive(Debug, Default, Clone)]
pub struct Query {
    pub genre: Option<String>,
    pub bpm: Option<String>,
    pub kit: Option<String>,
}

pub struct Catalog {
    grooves: Vec<Groove>,
    by_id: HashMap<String, usize>,
}

fn matches(values: &[String], wanted: &Option<String>) -> bool {
    match wanted {
        None => true,
        Some(value) => values.iter().any(|held| held == value),
    }
}

impl Catalog {
    pub fn from_str(raw: &str) -> Result<Self, &'static str> {
        let export: Export = serde_json::from_str(raw).map_err(|_| "EXPORT_MALFORMED")?;
        if export.schema != EXPORT_SCHEMA {
            return Err("EXPORT_SCHEMA_UNSUPPORTED");
        }
        let mut grooves = export.grooves;
        // Ordered once, at load, so every search answers in the same order
        // without sorting per request.
        grooves.sort_by(|left, right| left.id.cmp(&right.id));
        let by_id = grooves
            .iter()
            .enumerate()
            .map(|(index, groove)| (groove.id.clone(), index))
            .collect();
        Ok(Self { grooves, by_id })
    }

    pub fn load(path: &Path) -> Result<Self, &'static str> {
        let raw = fs::read_to_string(path).map_err(|_| "EXPORT_UNREADABLE")?;
        Self::from_str(&raw)
    }

    pub fn search(&self, query: &Query) -> Vec<&Groove> {
        self.grooves
            .iter()
            .filter(|groove| {
                matches(&groove.genre, &query.genre)
                    && matches(&groove.bpm, &query.bpm)
                    && matches(&groove.kit, &query.kit)
            })
            .collect()
    }

    pub fn groove(&self, id: &str) -> Option<&Groove> {
        self.by_id.get(id).map(|index| &self.grooves[*index])
    }

    /// Used at startup: an export that parses but holds nothing is a broken
    /// package, not a seed with no grooves in it.
    pub fn is_empty(&self) -> bool {
        self.grooves.is_empty()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE: &str = r#"{
        "schema": "groove.export.v1",
        "grooves": [
            {"id":"a1","genre":["metal"],"bpm":["bpm_140_159"],"kit":["kick","snare"],
             "bars":4,"meter":"4/4","ppq":480,"notes":[[36,0,120,100]]},
            {"id":"b2","genre":["rock","pop_rock_country"],"bpm":["bpm_120_139"],
             "kit":["kick","hat_open"],"bars":2,"meter":"4/4","ppq":480,
             "notes":[[36,0,120,90],[42,240,60,70]]}
        ]
    }"#;

    fn catalog() -> Catalog {
        Catalog::from_str(SAMPLE).expect("sample parses")
    }

    #[test]
    fn rejects_an_export_of_the_wrong_schema() {
        let wrong = r#"{"schema":"groove.export.v2","grooves":[]}"#;
        assert!(Catalog::from_str(wrong).is_err());
    }

    #[test]
    fn an_empty_filter_returns_everything() {
        let held = catalog();
        let hits = held.search(&Query::default());
        assert_eq!(hits.len(), 2);
    }

    #[test]
    fn filters_combine_as_and_across_axes() {
        let query = Query {
            genre: Some("rock".into()),
            bpm: Some("bpm_140_159".into()),
            kit: None,
        };
        let held = catalog();
        assert!(held.search(&query).is_empty());
    }

    #[test]
    fn a_groove_matches_any_of_its_own_values_on_one_axis() {
        // The genre axis carries both vocabularies at once, so a groove filed
        // as rock and pop_rock_country has to answer to either.
        let by_path = Query {
            genre: Some("rock".into()),
            ..Query::default()
        };
        let by_vendor = Query {
            genre: Some("pop_rock_country".into()),
            ..Query::default()
        };
        let held = catalog();
        assert_eq!(held.search(&by_path)[0].id, "b2");
        assert_eq!(held.search(&by_vendor)[0].id, "b2");
    }

    #[test]
    fn results_are_ordered_by_id_so_two_runs_agree() {
        let held = catalog();
        let hits = held.search(&Query::default());
        assert_eq!(hits[0].id, "a1");
        assert_eq!(hits[1].id, "b2");
    }

    #[test]
    fn a_groove_is_fetched_by_its_id_and_missing_ids_are_none() {
        let held = catalog();
        assert_eq!(held.groove("b2").unwrap().notes.len(), 2);
        assert!(held.groove("nope").is_none());
    }
}
