use pyo3::exceptions::{PyRuntimeError, PyTimeoutError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyString};
use regex::Regex;
use reqwest::blocking::Client;
use std::collections::BTreeMap;
use std::io::Read;
use std::sync::OnceLock;
use std::time::Duration;

type HttpResponse<'py> = (u16, Vec<(String, String)>, Bound<'py, PyBytes>);

fn refs() -> &'static Regex {
    static REFS: OnceLock<Regex> = OnceLock::new();
    REFS.get_or_init(|| Regex::new(r"\[ref=(?:f\d+)?e\d+\]").unwrap())
}

fn line_breaks() -> &'static Regex {
    static BREAKS: OnceLock<Regex> = OnceLock::new();
    // Match Python str.splitlines, including CRLF and Unicode separators.
    BREAKS.get_or_init(|| {
        Regex::new(r"\r\n|[\n\r\x0b\x0c\x1c-\x1e\x{0085}\x{2028}\x{2029}]").unwrap()
    })
}

fn select_lines(
    tree: &str,
    folded_tree: &str,
    names: &[String],
    terms: &[String],
) -> (Vec<String>, usize) {
    let mut lines: Vec<&str> = line_breaks().split(tree).collect();
    if lines.last() == Some(&"") {
        lines.pop();
    }
    let total = lines.len();
    let folded_lines: Vec<&str> = line_breaks().split(folded_tree).collect();
    // Only normalize and rank once per line. Ordered buckets preserve the
    // original score/index order without sorting the full accessibility tree.
    let mut buckets: BTreeMap<usize, Vec<(usize, String)>> = BTreeMap::new();
    for (index, line) in lines.iter().enumerate() {
        let clean = refs().replace_all(line, "[ref]");
        if clean.chars().count() > 800 {
            continue;
        }
        let folded = folded_lines[index];
        let score = usize::from(names.iter().any(|name| folded.contains(name))) * 100
            + terms
                .iter()
                .filter(|term| folded.contains(term.as_str()))
                .count();
        buckets
            .entry(score)
            .or_default()
            .push((index, clean.into_owned()));
    }
    let mut budget = 4800;
    let mut selected = Vec::new();
    'scores: for entries in buckets.values().rev() {
        for (index, line) in entries {
            if selected.len() == 32 {
                break 'scores;
            }
            let cost = line.chars().count() + 1;
            if cost <= budget {
                budget -= cost;
                selected.push((*index, line.clone()));
            }
        }
    }
    selected.sort_unstable_by_key(|(index, _)| *index);
    (selected.into_iter().map(|(_, line)| line).collect(), total)
}

#[pyfunction]
fn normalize_refs(py: Python<'_>, tree: String) -> String {
    py.detach(move || refs().replace_all(&tree, "[ref]").into_owned())
}

#[pyfunction]
fn compact_lines(
    py: Python<'_>,
    tree: String,
    names: Vec<String>,
    terms: Vec<String>,
) -> PyResult<(Vec<String>, usize)> {
    // One C-level fold of the whole tree keeps the host Python Unicode version,
    // including expanding folds (ß -> ss), without folding each line per term.
    let folded_tree: String = PyString::new(py, &tree)
        .call_method0("casefold")?
        .extract()?;
    Ok(py.detach(move || select_lines(&tree, &folded_tree, &names, &terms)))
}

#[pyclass]
struct HttpClient {
    client: Client,
}

#[pymethods]
impl HttpClient {
    #[new]
    fn new(py: Python<'_>) -> PyResult<Self> {
        py.detach(|| {
            let client = Client::builder()
                .redirect(reqwest::redirect::Policy::none())
                .retry(reqwest::retry::never())
                .pool_max_idle_per_host(8)
                .build()
                .map_err(|_| PyRuntimeError::new_err("Rust HTTP client configuration failed"))?;
            Ok(Self { client })
        })
    }

    fn request<'py>(
        &self,
        py: Python<'py>,
        method: String,
        url: String,
        headers: Vec<(String, String)>,
        body: Vec<u8>,
        timeout_s: f64,
    ) -> PyResult<HttpResponse<'py>> {
        if !timeout_s.is_finite() || !(1.0..=60.0).contains(&timeout_s) {
            return Err(PyValueError::new_err(
                "timeout must be between 1 and 60 seconds",
            ));
        }
        let result = py.detach(|| {
            let method = reqwest::Method::from_bytes(method.as_bytes())
                .map_err(|_| PyValueError::new_err("Invalid HTTP method"))?;
            let mut request = self
                .client
                .request(method, url)
                .timeout(Duration::from_secs_f64(timeout_s))
                .body(body);
            for (key, value) in headers {
                request = request.header(key, value);
            }
            let mut response = request.send().map_err(http_error)?;
            let status = response.status().as_u16();
            let headers = response
                .headers()
                .iter()
                .filter_map(|(key, value)| {
                    value
                        .to_str()
                        .ok()
                        .map(|value| (key.to_string(), value.to_string()))
                })
                .collect();
            // A provider response must not allocate arbitrary memory.
            let mut body = Vec::new();
            response
                .by_ref()
                .take(2_000_001)
                .read_to_end(&mut body)
                .map_err(|error| {
                    if error.kind() == std::io::ErrorKind::TimedOut
                        || error
                            .get_ref()
                            .and_then(|e| e.downcast_ref::<reqwest::Error>())
                            .is_some_and(|e| e.is_timeout())
                    {
                        PyTimeoutError::new_err("Rust HTTP deadline exceeded")
                    } else {
                        PyRuntimeError::new_err("Rust HTTP response read failed")
                    }
                })?;
            if body.len() > 2_000_000 {
                return Err(PyRuntimeError::new_err(
                    "Rust HTTP response exceeds size limit",
                ));
            }
            Ok((status, headers, body))
        })?;
        Ok((result.0, result.1, PyBytes::new(py, &result.2)))
    }
}

fn http_error(error: reqwest::Error) -> PyErr {
    // Do not expose URLs, authorization headers, or provider response bodies.
    if error.is_timeout() {
        PyTimeoutError::new_err("Rust HTTP deadline exceeded")
    } else {
        PyRuntimeError::new_err("Rust HTTP request failed")
    }
}

#[pymodule]
fn _aside_jev_native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(normalize_refs, module)?)?;
    module.add_function(wrap_pyfunction!(compact_lines, module)?)?;
    module.add_class::<HttpClient>()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reference_normalization_preserves_content() {
        assert_eq!(
            refs().replace_all("[ref=f2e19] [ref=e4] [ref=other]", "[ref]"),
            "[ref] [ref] [ref=other]"
        );
    }

    #[test]
    fn keeps_relevant_tail_in_document_order() {
        let tree =
            "- text Unrelated\n".repeat(5000) + "- link Continue [ref=e8]\n- heading Finished";
        let (lines, total) = select_lines(
            &tree,
            &tree.to_lowercase(),
            &["continue".into()],
            &["finished".into()],
        );
        assert_eq!(total, 5002);
        assert_eq!(lines.len(), 32);
        assert!(lines[30].contains("Continue [ref]"));
        assert!(lines[31].contains("Finished"));
    }

    #[test]
    fn unicode_casefold_and_splitlines() {
        let (lines, total) = select_lines(
            "noise\r\nStraße\u{2028}완료\n",
            "noise\r\nstrasse\u{2028}완료\n",
            &[],
            &["strasse".into()],
        );
        assert_eq!(total, 3);
        assert_eq!(lines, vec!["noise", "Straße", "완료"]);
        assert_eq!(select_lines("", "", &[], &[]).1, 0);
    }
}
