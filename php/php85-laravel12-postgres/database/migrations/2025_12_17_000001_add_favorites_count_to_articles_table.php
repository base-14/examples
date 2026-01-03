<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('articles', function (Blueprint $table) {
            $table->unsignedInteger('favorites_count')->default(0)->after('body');
        });

        DB::statement('
            UPDATE articles
            SET favorites_count = (
                SELECT COUNT(*) FROM article_user WHERE article_user.article_id = articles.id
            )
        ');
    }

    public function down(): void
    {
        Schema::table('articles', function (Blueprint $table) {
            $table->dropColumn('favorites_count');
        });
    }
};
