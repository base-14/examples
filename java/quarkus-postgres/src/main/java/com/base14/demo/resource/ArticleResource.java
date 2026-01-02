package com.base14.demo.resource;

import com.base14.demo.dto.ArticleDto.ArticleListResponse;
import com.base14.demo.dto.ArticleDto.ArticleWrapper;
import com.base14.demo.dto.ArticleDto.CreateArticleRequest;
import com.base14.demo.dto.ArticleDto.UpdateArticleRequest;
import com.base14.demo.dto.AuthDto.ErrorResponse;
import com.base14.demo.entity.Article;
import com.base14.demo.service.ArticleService;
import com.base14.demo.service.ServiceException;
import io.opentelemetry.api.trace.Span;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.RolesAllowed;
import jakarta.inject.Inject;
import jakarta.ws.rs.Consumes;
import jakarta.ws.rs.DELETE;
import jakarta.ws.rs.DefaultValue;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.PUT;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.PathParam;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.QueryParam;
import jakarta.ws.rs.core.Context;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import jakarta.ws.rs.core.SecurityContext;
import org.eclipse.microprofile.jwt.JsonWebToken;

@Path("/api/articles")
@Produces(MediaType.APPLICATION_JSON)
@Consumes(MediaType.APPLICATION_JSON)
public class ArticleResource {

    @Inject
    ArticleService articleService;

    @Inject
    JsonWebToken jwt;

    @GET
    @PermitAll
    public Response list(
            @QueryParam("limit") @DefaultValue("20") int limit,
            @QueryParam("offset") @DefaultValue("0") int offset) {
        try {
            Long userId = getCurrentUserId();
            if (limit > 100) limit = 100;
            ArticleListResponse response = articleService.list(limit, offset, userId);
            return Response.ok(response).build();
        } catch (ServiceException e) {
            return errorResponse(Response.Status.fromStatusCode(e.getStatusCode()), e.getMessage());
        }
    }

    @GET
    @Path("/{slug}")
    @PermitAll
    public Response get(@PathParam("slug") String slug) {
        try {
            Long userId = getCurrentUserId();
            Article article = articleService.getBySlug(slug, userId);
            return Response.ok(ArticleWrapper.from(article)).build();
        } catch (ServiceException e) {
            return errorResponse(Response.Status.fromStatusCode(e.getStatusCode()), e.getMessage());
        }
    }

    @POST
    @RolesAllowed("user")
    public Response create(CreateArticleRequest request) {
        if (request.title() == null || request.title().isBlank() ||
            request.body() == null || request.body().isBlank()) {
            return errorResponse(Response.Status.BAD_REQUEST, "title and body are required");
        }

        try {
            Long userId = Long.parseLong(jwt.getSubject());
            Article article = articleService.create(request, userId);
            return Response.status(Response.Status.CREATED)
                    .entity(ArticleWrapper.from(article))
                    .build();
        } catch (ServiceException e) {
            return errorResponse(Response.Status.fromStatusCode(e.getStatusCode()), e.getMessage());
        }
    }

    @PUT
    @Path("/{slug}")
    @RolesAllowed("user")
    public Response update(@PathParam("slug") String slug, UpdateArticleRequest request) {
        try {
            Long userId = Long.parseLong(jwt.getSubject());
            Article article = articleService.update(slug, request, userId);
            return Response.ok(ArticleWrapper.from(article)).build();
        } catch (ServiceException e) {
            return errorResponse(Response.Status.fromStatusCode(e.getStatusCode()), e.getMessage());
        }
    }

    @DELETE
    @Path("/{slug}")
    @RolesAllowed("user")
    public Response delete(@PathParam("slug") String slug) {
        try {
            Long userId = Long.parseLong(jwt.getSubject());
            articleService.delete(slug, userId);
            return Response.noContent().build();
        } catch (ServiceException e) {
            return errorResponse(Response.Status.fromStatusCode(e.getStatusCode()), e.getMessage());
        }
    }

    @POST
    @Path("/{slug}/favorite")
    @RolesAllowed("user")
    public Response favorite(@PathParam("slug") String slug) {
        try {
            Long userId = Long.parseLong(jwt.getSubject());
            Article article = articleService.favorite(slug, userId);
            return Response.ok(ArticleWrapper.from(article)).build();
        } catch (ServiceException e) {
            return errorResponse(Response.Status.fromStatusCode(e.getStatusCode()), e.getMessage());
        }
    }

    @DELETE
    @Path("/{slug}/favorite")
    @RolesAllowed("user")
    public Response unfavorite(@PathParam("slug") String slug) {
        try {
            Long userId = Long.parseLong(jwt.getSubject());
            Article article = articleService.unfavorite(slug, userId);
            return Response.ok(ArticleWrapper.from(article)).build();
        } catch (ServiceException e) {
            return errorResponse(Response.Status.fromStatusCode(e.getStatusCode()), e.getMessage());
        }
    }

    private Long getCurrentUserId() {
        try {
            String subject = jwt.getSubject();
            return subject != null ? Long.parseLong(subject) : null;
        } catch (Exception e) {
            return null;
        }
    }

    private Response errorResponse(Response.Status status, String message) {
        String traceId = Span.current().getSpanContext().getTraceId();
        return Response.status(status)
                .entity(new ErrorResponse(message, traceId))
                .build();
    }
}
