package handlers

import (
	"net/http"

	"github.com/base14/examples/go119-gin191-postgres/internal/logging"
	"github.com/base14/examples/go119-gin191-postgres/internal/models"
	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
	"gorm.io/gorm"
)

var tracer = otel.Tracer("user-handler")

type UserHandler struct {
	db *gorm.DB
}

func NewUserHandler(db *gorm.DB) *UserHandler {
	return &UserHandler{db: db}
}

// ListUsers returns all users
func (h *UserHandler) ListUsers(c *gin.Context) {
	ctx, span := tracer.Start(c.Request.Context(), "ListUsers",
		trace.WithSpanKind(trace.SpanKindServer))
	defer span.End()

	var users []models.User
	result := h.db.WithContext(ctx).Find(&users)
	if result.Error != nil {
		span.RecordError(result.Error)
		span.SetStatus(codes.Error, "failed to fetch users")
		c.JSON(http.StatusInternalServerError, gin.H{"error": result.Error.Error()})
		return
	}

	span.SetAttributes(attribute.Int("user.count", len(users)))
	c.JSON(http.StatusOK, models.UsersResponse{
		Users: users,
		Count: len(users),
	})
}

// GetUser returns a single user by ID
func (h *UserHandler) GetUser(c *gin.Context) {
	ctx, span := tracer.Start(c.Request.Context(), "GetUser",
		trace.WithSpanKind(trace.SpanKindServer))
	defer span.End()

	userID, err := uuid.Parse(c.Param("id"))
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "invalid user ID")
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid user ID"})
		return
	}

	span.SetAttributes(attribute.String("user.id", userID.String()))

	var user models.User
	result := h.db.WithContext(ctx).First(&user, "id = ?", userID)
	if result.Error != nil {
		if result.Error == gorm.ErrRecordNotFound {
			span.SetStatus(codes.Error, "user not found")
			c.JSON(http.StatusNotFound, gin.H{"error": "user not found"})
			return
		}
		span.RecordError(result.Error)
		span.SetStatus(codes.Error, "database error")
		c.JSON(http.StatusInternalServerError, gin.H{"error": result.Error.Error()})
		return
	}

	c.JSON(http.StatusOK, models.UserResponse{User: user})
}

// CreateUser creates a new user
func (h *UserHandler) CreateUser(c *gin.Context) {
	ctx, span := tracer.Start(c.Request.Context(), "CreateUser",
		trace.WithSpanKind(trace.SpanKindServer))
	defer span.End()

	logging.Info(ctx, "Received request to create new user")

	var req models.CreateUserRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		logging.WithFields(ctx, map[string]interface{}{
			"error": err.Error(),
		}).Error("Failed to parse request body")
		span.RecordError(err)
		span.SetStatus(codes.Error, "invalid request body")
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	user := models.User{
		Email: req.Email,
		Name:  req.Name,
		Bio:   req.Bio,
		Image: req.Image,
	}

	span.SetAttributes(
		attribute.String("user.email", user.Email),
		attribute.String("user.name", user.Name),
	)

	logging.WithFields(ctx, map[string]interface{}{
		"user.email": user.Email,
		"user.name":  user.Name,
	}).Info("Creating user in database")

	result := h.db.WithContext(ctx).Create(&user)
	if result.Error != nil {
		logging.WithFields(ctx, map[string]interface{}{
			"error":      result.Error.Error(),
			"user.email": user.Email,
		}).Error("Failed to create user in database")
		span.RecordError(result.Error)
		span.SetStatus(codes.Error, "failed to create user")
		c.JSON(http.StatusInternalServerError, gin.H{"error": result.Error.Error()})
		return
	}

	span.SetAttributes(attribute.String("user.id", user.ID.String()))
	span.AddEvent("user_created")

	logging.WithFields(ctx, map[string]interface{}{
		"user.id":    user.ID.String(),
		"user.email": user.Email,
	}).Info("User created successfully")

	c.JSON(http.StatusCreated, models.UserResponse{User: user})
}

// UpdateUser updates an existing user
func (h *UserHandler) UpdateUser(c *gin.Context) {
	ctx, span := tracer.Start(c.Request.Context(), "UpdateUser",
		trace.WithSpanKind(trace.SpanKindServer))
	defer span.End()

	userID, err := uuid.Parse(c.Param("id"))
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "invalid user ID")
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid user ID"})
		return
	}

	span.SetAttributes(attribute.String("user.id", userID.String()))

	var req models.UpdateUserRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "invalid request body")
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	var user models.User
	result := h.db.WithContext(ctx).First(&user, "id = ?", userID)
	if result.Error != nil {
		if result.Error == gorm.ErrRecordNotFound {
			span.SetStatus(codes.Error, "user not found")
			c.JSON(http.StatusNotFound, gin.H{"error": "user not found"})
			return
		}
		span.RecordError(result.Error)
		span.SetStatus(codes.Error, "database error")
		c.JSON(http.StatusInternalServerError, gin.H{"error": result.Error.Error()})
		return
	}

	// Update only provided fields
	updates := make(map[string]interface{})
	if req.Name != nil {
		updates["name"] = *req.Name
	}
	if req.Bio != nil {
		updates["bio"] = *req.Bio
	}
	if req.Image != nil {
		updates["image"] = *req.Image
	}

	if len(updates) > 0 {
		result = h.db.WithContext(ctx).Model(&user).Updates(updates)
		if result.Error != nil {
			span.RecordError(result.Error)
			span.SetStatus(codes.Error, "failed to update user")
			c.JSON(http.StatusInternalServerError, gin.H{"error": result.Error.Error()})
			return
		}
	}

	span.AddEvent("user_updated")
	c.JSON(http.StatusOK, models.UserResponse{User: user})
}

// DeleteUser deletes a user
func (h *UserHandler) DeleteUser(c *gin.Context) {
	ctx, span := tracer.Start(c.Request.Context(), "DeleteUser",
		trace.WithSpanKind(trace.SpanKindServer))
	defer span.End()

	userID, err := uuid.Parse(c.Param("id"))
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "invalid user ID")
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid user ID"})
		return
	}

	span.SetAttributes(attribute.String("user.id", userID.String()))

	result := h.db.WithContext(ctx).Delete(&models.User{}, "id = ?", userID)
	if result.Error != nil {
		span.RecordError(result.Error)
		span.SetStatus(codes.Error, "failed to delete user")
		c.JSON(http.StatusInternalServerError, gin.H{"error": result.Error.Error()})
		return
	}

	if result.RowsAffected == 0 {
		span.SetStatus(codes.Error, "user not found")
		c.JSON(http.StatusNotFound, gin.H{"error": "user not found"})
		return
	}

	span.AddEvent("user_deleted")
	c.JSON(http.StatusOK, gin.H{"message": "user deleted successfully"})
}
