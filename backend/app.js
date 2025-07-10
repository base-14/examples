'use strict';
require('./instrumentation');
// const { setupTelemetry } = require('./telemetry');
// setupTelemetry();
// load modules
const express = require('express');
const morgan = require('morgan');
const { sequelize } = require('./models');
const cors = require('cors');
const { metrics } = require('@opentelemetry/api');
const logAPI = require('@opentelemetry/api-logs');

// variable to enable global error logging
const enableGlobalErrorLogging = process.env.enableGlobalErrorLogging === 'true';

const userRouter = require('./routes/users');
const courseRouter = require('./routes/courses');

// create the Express app
const app = express();

// setup morgan which gives us http request logging
app.use(morgan('dev'));

// set up cors 
app.use(cors());

// set up Express to work with JSON
app.use(express.json());

const meter = metrics.getMeter('course-management-app-backend');
const requestCounter = meter.createCounter('http_requests_total', {
  description: 'Total number of HTTP requests',
});

const requestDurationHistogram = meter.createHistogram('http_request_duration_seconds', {
  description: 'HTTP request duration in seconds',
  boundaries: [0.01, 0.05, 0.1, 0.5, 1, 5]
});

// Metrics middleware for request tracking
app.use((req, res, next) => {
  const startTime = performance.now();
  
  // Count the request
  requestCounter.add(1, {
    method: req.method,
    route: req.route?.path || 'unknown',
  });
  
  // Track duration on response finish
  res.on('finish', () => {
    const duration = (performance.now() - startTime) / 1000; // Convert to seconds
    requestDurationHistogram.record(duration, {
      method: req.method,
      route: req.route?.path || 'unknown',
      status: res.statusCode,
    });
  });
  
  next();
});


// setup a friendly greeting for the root route
app.get('/', (req, res) => {
  res.json({
    message: 'Welcome to the REST API project!',
  });
});

// Add routes
app.use('/api', userRouter);
app.use('/api', courseRouter);

// send 404 if no other route matched
app.use((req, res) => {
  res.status(404).json({
    message: 'Route Not Found',
  });
});

// setup a global error handler
app.use((err, req, res, next) => {
  if (enableGlobalErrorLogging) {
    console.error(`Global error handler: ${JSON.stringify(err.stack)}`);
  }

  res.status(err.status || 500).json({
    message: err.message,
    error: {},
  });
});

// set our port
app.set('port', process.env.PORT || 5001);

// Test the database connection
(async () => {
  try {
    await sequelize.authenticate();
    console.log('Connection has been established successfully.');
  } catch (error) {
    console.error('Unable to connect to the database: ', error);
  }
})();

// start listening on our port
sequelize.sync()
  .then(() => {
    const server = app.listen(app.get('port'), () => {
      console.log(`Express server is listening on port ${server.address().port}`);
    });
  });