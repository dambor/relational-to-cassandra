// BACKEND SERVER - app.js
// This file should be placed in the root directory of your project
const express = require('express');
const { exec } = require('child_process');
const mysql = require('mysql2/promise');
const cassandra = require('cassandra-driver');
const bodyParser = require('body-parser');
const fs = require('fs').promises;
const path = require('path');
const multer = require('multer');
const temp = require('temp');
const app = express();
const port = process.env.PORT || 3000;

// Auto-track and cleanup temp files
temp.track();

// Configure multer for file uploads
const upload = multer({ 
  storage: multer.memoryStorage(),
  limits: { fileSize: 10 * 1024 * 1024 } // 10MB limit
});

// Middleware
app.use(bodyParser.json());
app.use(bodyParser.urlencoded({ extended: true }));
app.use(express.static('public'));

// Routes
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// Test MySQL Connection
app.post('/api/test-mysql', async (req, res) => {
  const { host, port, user, password, database } = req.body;
  
  try {
    const connection = await mysql.createConnection({
      host,
      port: port || 3306,
      user,
      password,
      database
    });
    
    await connection.ping();
    await connection.end();
    
    res.json({ success: true, message: 'MySQL connection successful!' });
  } catch (error) {
    res.status(400).json({ 
      success: false, 
      message: 'MySQL connection failed', 
      error: error.message 
    });
  }
});

// Test Cassandra Connection
app.post('/api/test-cassandra', async (req, res) => {
  const { contactPoints, localDataCenter, keyspace, username, password } = req.body;
  
  try {
    const authProvider = username && password 
      ? new cassandra.auth.PlainTextAuthProvider(username, password)
      : undefined;
    
    const client = new cassandra.Client({
      contactPoints: contactPoints.split(','),
      localDataCenter,
      keyspace,
      authProvider
    });
    
    await client.connect();
    await client.shutdown();
    
    res.json({ success: true, message: 'Cassandra connection successful!' });
  } catch (error) {
    res.status(400).json({ 
      success: false, 
      message: 'Cassandra connection failed', 
      error: error.message 
    });
  }
});

// Extract MySQL Schema
app.post('/api/extract-mysql-schema', async (req, res) => {
  const { host, port, user, password, database } = req.body;
  
  try {
    const connection = await mysql.createConnection({
      host,
      port: port || 3306,
      user,
      password,
      database
    });
    
    // Get tables
    const [tables] = await connection.execute(
      'SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = ?', 
      [database]
    );
    
    const schema = {
      tables: []
    };
    
    // Process each table
    for (const table of tables) {
      const tableName = table.TABLE_NAME;
      
      // Get columns
      const [columns] = await connection.execute(
        `SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_KEY, EXTRA 
         FROM INFORMATION_SCHEMA.COLUMNS 
         WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
         ORDER BY ORDINAL_POSITION`,
        [database, tableName]
      );
      
      // Get foreign keys
      const [foreignKeys] = await connection.execute(
        `SELECT 
           COLUMN_NAME as column_name,
           REFERENCED_TABLE_NAME as ref_table,
           REFERENCED_COLUMN_NAME as ref_column
         FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
         WHERE TABLE_SCHEMA = ? 
           AND TABLE_NAME = ?
           AND REFERENCED_TABLE_NAME IS NOT NULL`,
        [database, tableName]
      );
      
      // Format columns and foreign keys
      const formattedColumns = columns.map(col => ({
        name: col.COLUMN_NAME,
        type: col.DATA_TYPE,
        nullable: col.IS_NULLABLE === 'YES',
        primary_key: col.COLUMN_KEY === 'PRI'
      }));
      
      const formattedForeignKeys = foreignKeys.map(fk => ({
        column: fk.column_name,
        references: {
          table: fk.ref_table,
          column: fk.ref_column
        }
      }));
      
      schema.tables.push({
        name: tableName,
        columns: formattedColumns,
        foreign_keys: formattedForeignKeys
      });
    }
    
    await connection.end();
    
    res.json({ 
      success: true, 
      message: 'Schema extracted successfully', 
      schema 
    });
  } catch (error) {
    res.status(400).json({ 
      success: false, 
      message: 'Failed to extract schema', 
      error: error.message 
    });
  }
});

// Convert Schema
app.post('/api/convert-schema', upload.fields([
  { name: 'schemaFile', maxCount: 1 }, 
  { name: 'queriesFile', maxCount: 1 }
]), async (req, res) => {
  try {
    let schemaContent;
    
    // Get schema from file upload or request body
    if (req.files && req.files.schemaFile && req.files.schemaFile[0]) {
      schemaContent = req.files.schemaFile[0].buffer.toString('utf8');
    } else if (req.body.schema) {
      schemaContent = typeof req.body.schema === 'string' 
        ? req.body.schema 
        : JSON.stringify(req.body.schema);
    } else {
      return res.status(400).json({
        success: false,
        message: 'No schema provided'
      });
    }
    
    // Create temporary files
    const schemaFilePath = await temp.open({ prefix: 'schema-', suffix: '.json' });
    await fs.writeFile(schemaFilePath.path, schemaContent);
    
    let queriesFilePath = null;
    if (req.files && req.files.queriesFile && req.files.queriesFile[0]) {
      queriesFilePath = await temp.open({ prefix: 'queries-', suffix: '.txt' });
      await fs.writeFile(queriesFilePath.path, req.files.queriesFile[0].buffer);
    } else if (req.body.queries) {
      queriesFilePath = await temp.open({ prefix: 'queries-', suffix: '.txt' });
      await fs.writeFile(queriesFilePath.path, req.body.queries);
    }
    
    // Create output files
    const outputFilePath = await temp.open({ prefix: 'output-', suffix: '.cql' });
    const summaryFilePath = await temp.open({ prefix: 'summary-', suffix: '.md' });
    
    // Build command
    let command = `python3 rel_to_cassandra.py --input ${schemaFilePath.path} --output ${outputFilePath.path} --summary ${summaryFilePath.path}`;
    if (queriesFilePath) {
      command += ` --queries ${queriesFilePath.path}`;
    }
    
    // Run the conversion script
    exec(command, async (error, stdout, stderr) => {
      if (error) {
        return res.status(400).json({
          success: false,
          message: 'Conversion failed',
          error: error.message,
          stderr
        });
      }
      
      try {
        // Read output files
        const cqlOutput = await fs.readFile(outputFilePath.path, 'utf8');
        const summaryOutput = await fs.readFile(summaryFilePath.path, 'utf8');
        
        res.json({
          success: true,
          message: 'Conversion completed successfully',
          stdout,
          cqlOutput,
          summaryOutput
        });
      } catch (readError) {
        res.status(500).json({
          success: false,
          message: 'Failed to read output files',
          error: readError.message
        });
      }
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      message: 'Server error during conversion',
      error: error.message
    });
  }
});

// Deploy to Cassandra
app.post('/api/deploy-to-cassandra', async (req, res) => {
  const { 
    contactPoints, 
    localDataCenter, 
    keyspace, 
    username, 
    password, 
    cqlScript 
  } = req.body;
  
  try {
    const authProvider = username && password 
      ? new cassandra.auth.PlainTextAuthProvider(username, password)
      : undefined;
    
    // Connect without keyspace first to create it if needed
    const client = new cassandra.Client({
      contactPoints: contactPoints.split(','),
      localDataCenter,
      authProvider
    });
    
    await client.connect();
    
    // Split the CQL script into individual statements
    const statements = cqlScript
      .split(';')
      .map(stmt => stmt.trim())
      .filter(stmt => stmt && !stmt.startsWith('--'));
    
    const results = [];
    
    // Execute each statement
    for (let stmt of statements) {
      try {
        // Skip USE statement as we'll handle keyspaces explicitly
        if (stmt.toLowerCase().startsWith('use ')) {
          const keyspaceName = stmt.substring(4).trim();
          await client.execute(`CREATE KEYSPACE IF NOT EXISTS ${keyspaceName} WITH REPLICATION = {'class': 'SimpleStrategy', 'replication_factor': 1}`);
          client.keyspace = keyspaceName;
          results.push({ 
            statement: stmt, 
            success: true, 
            message: `Switched to keyspace ${keyspaceName}` 
          });
          continue;
        }
        
        // Add semicolon back for execution
        if (!stmt.endsWith(';')) {
          stmt += ';';
        }
        
        await client.execute(stmt);
        results.push({ statement: stmt, success: true });
      } catch (stmtError) {
        results.push({ 
          statement: stmt, 
          success: false, 
          error: stmtError.message 
        });
      }
    }
    
    await client.shutdown();
    
    // Check if all statements succeeded
    const allSucceeded = results.every(r => r.success);
    
    res.json({
      success: allSucceeded,
      message: allSucceeded ? 'All statements executed successfully' : 'Some statements failed',
      results
    });
  } catch (error) {
    res.status(400).json({
      success: false,
      message: 'Failed to deploy to Cassandra',
      error: error.message
    });
  }
});

// Start server
app.listen(port, () => {
  console.log(`Server running on http://localhost:${port}`);
});
