using Api.Data.Entities;
using Microsoft.EntityFrameworkCore;

namespace Api.Data;

public class AppDbContext(DbContextOptions<AppDbContext> options) : DbContext(options)
{
    public DbSet<User> Users => Set<User>();
    public DbSet<Article> Articles => Set<Article>();
    public DbSet<Favorite> Favorites => Set<Favorite>();
    public DbSet<Job> Jobs => Set<Job>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<User>(entity =>
        {
            entity.HasIndex(e => e.Email).IsUnique();
        });

        modelBuilder.Entity<Article>(entity =>
        {
            entity.HasIndex(e => e.Slug).IsUnique();
            entity.HasOne(e => e.Author)
                .WithMany(u => u.Articles)
                .HasForeignKey(e => e.AuthorId)
                .OnDelete(DeleteBehavior.Cascade);
        });

        modelBuilder.Entity<Favorite>(entity =>
        {
            entity.HasIndex(e => new { e.UserId, e.ArticleId }).IsUnique();
            entity.HasOne(e => e.User)
                .WithMany(u => u.Favorites)
                .HasForeignKey(e => e.UserId)
                .OnDelete(DeleteBehavior.Cascade);
            entity.HasOne(e => e.Article)
                .WithMany(a => a.Favorites)
                .HasForeignKey(e => e.ArticleId)
                .OnDelete(DeleteBehavior.NoAction);
        });

        modelBuilder.Entity<Job>(entity =>
        {
            entity.HasIndex(e => new { e.Status, e.CreatedAt });
            entity.HasIndex(e => new { e.Status, e.NextRetryAt });
        });
    }
}
