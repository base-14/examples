use std::sync::LazyLock;

use regex::Regex;

pub const PROMPT_MAX_CHARS: usize = 1000;
pub const SYSTEM_MAX_CHARS: usize = 500;
pub const COMPLETION_MAX_CHARS: usize = 2000;

static EMAIL: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b").unwrap());

static CARD: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\b(?:\d{4}[-\s]?){3}\d{4}\b").unwrap());

static PHONE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?:\+?\d{1,2}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b").unwrap()
});

pub fn scrub(text: &str) -> String {
    if text.is_empty() {
        return String::new();
    }

    let without_emails = EMAIL.replace_all(text, "[EMAIL]");
    let without_cards = CARD.replace_all(&without_emails, "[CARD]");
    PHONE.replace_all(&without_cards, "[PHONE]").into_owned()
}

pub fn truncate(text: &str, max_chars: usize) -> String {
    text.chars().take(max_chars).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn scrubs_email_addresses() {
        assert_eq!(
            scrub("write to alex.chen@techwave.io today"),
            "write to [EMAIL] today"
        );
    }

    #[test]
    fn scrubs_card_like_numbers() {
        assert_eq!(scrub("card 4111 1111 1111 1111 ok"), "card [CARD] ok");
        assert_eq!(scrub("card 4111-1111-1111-1111 ok"), "card [CARD] ok");
        assert_eq!(scrub("card 4111111111111111 ok"), "card [CARD] ok");
    }

    #[test]
    fn scrubs_phone_numbers() {
        assert_eq!(scrub("call 415-555-0134 now"), "call [PHONE] now");
        assert_eq!(scrub("call +1 (415) 555-0134 now"), "call [PHONE] now");
    }

    #[test]
    fn leaves_clean_text_alone() {
        let text = "Unemployment fell to 3.7 percent in 2023.";
        assert_eq!(scrub(text), text);
    }

    #[test]
    fn scrubs_empty_text_to_empty() {
        assert_eq!(scrub(""), "");
    }

    #[test]
    fn truncate_keeps_short_text() {
        assert_eq!(truncate("hello", 10), "hello");
        assert_eq!(truncate("hello", 5), "hello");
    }

    #[test]
    fn truncate_cuts_long_text() {
        assert_eq!(truncate("hello world", 5), "hello");
    }

    #[test]
    fn truncate_counts_characters_not_bytes() {
        let result = truncate("hé世界!", 3);
        assert_eq!(result, "hé世");
        assert_eq!(result.chars().count(), 3);
    }
}
