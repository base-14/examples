const express = require('express');

const router = express.Router();
const User = require('../models').User;
const { authenticateUser } = require('../middleware/auth-user');
const { asyncHandler } = require('../middleware/async-handler');
const {trace, context} = require('@opentelemetry/api');
const tracer = trace.getTracer('course-management-app-backend');
const logAPI = require('@opentelemetry/api-logs');

const logger = logAPI.logs.getLogger('course-management-app-backend');
// Return the list of users
router.get('/users', authenticateUser, asyncHandler(async (req, res) => {
  const span = tracer.startSpan('get-users');
  const ctx = trace.setSpan(context.active(), span);
  
  try {
    context.with(ctx, async () => {
      span.setAttribute('http.url', req.url);
      span.setAttribute('http.method', req.method);   

      const user = req.currentUser;

      const userResult = await User.findOne({
        where: {
          emailAddress: user.emailAddress
        },
        attributes: {
          exclude: ['password', 'createdAt', 'updatedAt']
        }
      });
      logger.emit({
        body: 'Users found',
        severityNumber: logAPI.SeverityNumber.INFO,
        attributes: {
          user: userResult
        },
        traceId: span.traceId,
        spanId: span.spanId,
        
      });

      res.json(userResult);
    });
  } finally {
    span.end();
  }
}));

// Create a user
router.post('/users', asyncHandler(async (req, res) => {
  const span = tracer.startSpan('create-user');
  const ctx = trace.setSpan(context.active(), span);
  
  try {
    await context.with(ctx, async () => {
      span.setAttribute('http.url', req.url);
      span.setAttribute('http.method', req.method);
      
      await User.create(req.body);
      res.status(201)
        .location('/')
        .end();
    });
  } catch (error) {
    span.recordException(error);
    span.setStatus({ code: 2, message: error.message });
    
    if (error.name === 'SequelizeValidationError' || error.name === 'SequelizeUniqueConstraintError') {
      const errors = error.errors.map(err => err.message);
      res.status(400).json({ errors: errors });
    } else {
      res.status(400).json({ error: error.message });
    }
  } finally {
    span.end();
  }
}));

module.exports = router;