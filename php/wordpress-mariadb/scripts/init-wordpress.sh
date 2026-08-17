#!/bin/bash
# Idempotent WordPress install and content seed. Re-running is a no-op if the
# seed is complete, and fails loudly if an earlier run left it half-done.

set -euo pipefail

WP_URL="${WP_URL:-http://localhost:8080}"

if wp core is-installed 2>/dev/null; then
    missing=()

    post_count="$(wp post list --post_type=post --post_status=publish --category_name=observability --format=count)"
    [ "$post_count" -eq 3 ] || missing+=("expected 3 published posts in the observability category, found $post_count")

    about_count="$(wp post list --post_type=page --name=about --post_status=publish --format=count)"
    [ "$about_count" -eq 1 ] || missing+=("about page not found")

    first_post_id="$(wp post list --post_type=post --name=first-post --field=ID)"
    comment_count=0
    if [ -n "$first_post_id" ]; then
        comment_count="$(wp comment list --post_id="$first_post_id" --status=approve --format=count)"
    fi
    [ "$comment_count" -ge 1 ] || missing+=("no approved comment on first-post")

    if [ "${#missing[@]}" -eq 0 ]; then
        echo "WordPress already installed, skipping seed"
        exit 0
    fi

    echo "WordPress is installed but the seed is incomplete:"
    printf '  - %s\n' "${missing[@]}"
    exit 1
fi

wp core install \
    --url="$WP_URL" \
    --title="Scout WordPress OpenTelemetry Example" \
    --admin_user=admin \
    --admin_password=admin_password \
    --admin_email=admin@example.com \
    --skip-email

# Pretty permalinks put the route in the URL, which the capture needs.
wp rewrite structure '/%postname%/' --hard

wp term create category observability --slug=observability

CATEGORY_ID="$(wp term get category observability --by=slug --field=term_id)"

for slug in first-post second-post third-post; do
    wp post create \
        --post_type=post \
        --post_title="${slug//-/ }" \
        --post_name="$slug" \
        --post_content="Seed content for $slug. Mentions scout for the search path." \
        --post_status=publish \
        --post_category="$CATEGORY_ID"
done

wp post create \
    --post_type=page \
    --post_title="About" \
    --post_name=about \
    --post_content="Seed page." \
    --post_status=publish

FIRST_POST_ID="$(wp post list --post_type=post --name=first-post --field=ID)"

wp comment create \
    --comment_post_ID="$FIRST_POST_ID" \
    --comment_content="Seed comment." \
    --comment_author="Seed" \
    --comment_author_email="seed@example.com" \
    --comment_approved=1

echo "Seed complete"
