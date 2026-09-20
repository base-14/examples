const HTTPS_PORT: i64 = 443;
const OLLAMA_PORT: i64 = 11434;

pub fn semconv_name(provider: &str) -> &'static str {
    match provider {
        "anthropic" => "anthropic",
        "google" => "gcp.gemini",
        "ollama" => "ollama",
        _ => "openai",
    }
}

pub fn endpoint(provider: &str, ollama_base_url: &str) -> (String, i64) {
    match provider {
        "anthropic" => ("api.anthropic.com".to_string(), HTTPS_PORT),
        "google" => ("generativelanguage.googleapis.com".to_string(), HTTPS_PORT),
        "ollama" => ollama_endpoint(ollama_base_url),
        _ => ("api.openai.com".to_string(), HTTPS_PORT),
    }
}

fn ollama_endpoint(base_url: &str) -> (String, i64) {
    let authority = base_url
        .split_once("://")
        .map_or(base_url, |(_, rest)| rest)
        .split('/')
        .next()
        .unwrap_or("");

    match authority.rsplit_once(':') {
        Some((host, port)) => (host_or_default(host), port.parse().unwrap_or(OLLAMA_PORT)),
        None => (host_or_default(authority), OLLAMA_PORT),
    }
}

fn host_or_default(host: &str) -> String {
    if host.is_empty() {
        "localhost".to_string()
    } else {
        host.to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_gemini_config_key_maps_to_the_gemini_semconv_name() {
        let config_key = "google";
        assert_eq!(semconv_name(config_key), "gcp.gemini");
    }

    #[test]
    fn known_providers_keep_their_names() {
        assert_eq!(semconv_name("anthropic"), "anthropic");
        assert_eq!(semconv_name("openai"), "openai");
        assert_eq!(semconv_name("ollama"), "ollama");
    }

    #[test]
    fn unknown_providers_fall_back_to_openai() {
        assert_eq!(semconv_name("something-else"), "openai");
    }

    #[test]
    fn cloud_providers_use_their_api_host_on_443() {
        assert_eq!(
            endpoint("anthropic", ""),
            ("api.anthropic.com".to_string(), 443)
        );
        assert_eq!(
            endpoint("google", ""),
            ("generativelanguage.googleapis.com".to_string(), 443)
        );
        assert_eq!(endpoint("openai", ""), ("api.openai.com".to_string(), 443));
    }

    #[test]
    fn ollama_takes_host_and_port_from_the_base_url() {
        assert_eq!(
            endpoint("ollama", "http://localhost:11434"),
            ("localhost".to_string(), 11434)
        );
        assert_eq!(
            endpoint("ollama", "http://host.docker.internal:11434/v1"),
            ("host.docker.internal".to_string(), 11434)
        );
        assert_eq!(
            endpoint("ollama", "http://ollama:9000"),
            ("ollama".to_string(), 9000)
        );
    }

    #[test]
    fn ollama_defaults_the_port_when_the_base_url_omits_it() {
        assert_eq!(
            endpoint("ollama", "http://ollama-host"),
            ("ollama-host".to_string(), 11434)
        );
        assert_eq!(endpoint("ollama", ""), ("localhost".to_string(), 11434));
    }
}
