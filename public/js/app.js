// FRONTEND JAVASCRIPT - public/js/app.js
// This file should be placed in the public/js directory
document.addEventListener('DOMContentLoaded', function() {
  // Initialize CodeMirror editors
  const editors = initializeEditors();
  
  // Current state
  let currentSchema = null;
  let currentQueries = null;
  let conversionOutput = {
    cql: null,
    summary: null
  };

  // Add event listeners
  addEventListeners(editors);

  // Tab navigation helpers
  function activateTab(tabId) {
    const tab = document.querySelector(`#mainTabs button[data-bs-target="#${tabId}"]`);
    const tabInstance = new bootstrap.Tab(tab);
    tabInstance.show();
  }

  // Initialize CodeMirror editors
  function initializeEditors() {
    const manualSchemaEditor = CodeMirror(document.getElementById('manualSchemaEditor'), {
      mode: 'application/json',
      theme: 'dracula',
      lineNumbers: true,
      lineWrapping: true,
      value: JSON.stringify({
        tables: [
          {
            name: "users",
            columns: [
              {name: "id", type: "int", primary_key: true},
              {name: "username", type: "varchar(255)"},
              {name: "email", type: "varchar(255)"}
            ]
          },
          {
            name: "posts",
            columns: [
              {name: "id", type: "int", primary_key: true},
              {name: "user_id", type: "int"},
              {name: "title", type: "varchar(255)"},
              {name: "content", type: "text"}
            ],
            foreign_keys: [
              {
                column: "user_id",
                references: {
                  table: "users",
                  column: "id"
                }
              }
            ]
          }
        ]
      }, null, 2)
    });

    const manualQueriesEditor = CodeMirror(document.getElementById('manualQueriesEditor'), {
      mode: 'text/x-sql',
      theme: 'dracula',
      lineNumbers: true,
      lineWrapping: true,
      value: 'SELECT * FROM users WHERE id = ?\nSELECT * FROM posts WHERE user_id = ?\nSELECT posts.*, users.username FROM posts JOIN users ON posts.user_id = users.id WHERE posts.id = ?'
    });

    const schemaEditor = CodeMirror(document.getElementById('schemaEditor'), {
      mode: 'application/json',
      theme: 'dracula',
      lineNumbers: true,
      lineWrapping: true,
      readOnly: true
    });

    const queriesEditor = CodeMirror(document.getElementById('queriesEditor'), {
      mode: 'text/x-sql',
      theme: 'dracula',
      lineNumbers: true,
      lineWrapping: true,
      readOnly: true
    });

    const cqlEditor = CodeMirror(document.getElementById('cqlEditor'), {
      mode: 'text/x-sql',
      theme: 'dracula',
      lineNumbers: true,
      lineWrapping: true,
      readOnly: true
    });

    const summaryEditor = CodeMirror(document.getElementById('summaryEditor'), {
      mode: 'text/markdown',
      theme: 'dracula',
      lineNumbers: true,
      lineWrapping: true,
      readOnly: true
    });

    const deployCqlEditor = CodeMirror(document.getElementById('deployCqlEditor'), {
      mode: 'text/x-sql',
      theme: 'dracula',
      lineNumbers: true,
      lineWrapping: true
    });

    return {
      manualSchemaEditor,
      manualQueriesEditor,
      schemaEditor,
      queriesEditor,
      cqlEditor,
      summaryEditor,
      deployCqlEditor
    };
  }

  // Add event listeners to UI elements
  function addEventListeners(editors) {
    // MySQL connection testing
    document.getElementById('testMysqlBtn').addEventListener('click', function() {
      testMysqlConnection();
    });

    // MySQL schema extraction
    document.getElementById('extractMysqlBtn').addEventListener('click', function() {
      extractMysqlSchema(editors);
    });

    // Load schema from file
    document.getElementById('loadSchemaFileBtn').addEventListener('click', function() {
      loadSchemaFromFile(editors);
    });

    // Load schema from manual entry
    document.getElementById('loadManualSchemaBtn').addEventListener('click', function() {
      loadManualSchema(editors);
    });

    // Edit schema button
    document.getElementById('editSchemaBtn').addEventListener('click', function() {
      editors.schemaEditor.setOption('readOnly', false);
      showAlert('Schema editor is now editable. Click "Convert to Cassandra" when done.', 'info');
    });

    // Edit queries button
    document.getElementById('editQueriesBtn').addEventListener('click', function() {
      editors.queriesEditor.setOption('readOnly', false);
      showAlert('Queries editor is now editable. Click "Convert to Cassandra" when done.', 'info');
    });

    // Convert schema button
    document.getElementById('convertSchemaBtn').addEventListener('click', function() {
      convertSchema(editors);
    });

    // Download CQL button
    document.getElementById('downloadCqlBtn').addEventListener('click', function() {
      downloadCql();
    });

    // Add Report button after Download CQL button
    document.getElementById('downloadCqlBtn').insertAdjacentHTML('afterend', 
      '<button type="button" id="generateReportBtn" class="btn btn-outline-info ms-2" disabled>Generate Report</button>');

    // Generate Report button
    document.getElementById('generateReportBtn').addEventListener('click', function() {
      generateReport(editors);
    });

    // Test Cassandra connection
    document.getElementById('testCassandraBtn').addEventListener('click', function() {
      testCassandraConnection();
    });

    // Deploy to Cassandra
    document.getElementById('deployCassandraBtn').addEventListener('click', function() {
      deployCassandraSchema();
    });

    // Update deploy CQL when changing tabs
    document.getElementById('deploy-tab').addEventListener('click', function() {
      if (conversionOutput.cql) {
        editors.deployCqlEditor.setValue(conversionOutput.cql);
      }
    });
  }

  // Test MySQL connection
  function testMysqlConnection() {
    const connection = getMysqlConnection();
    
    fetch('/api/test-mysql', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(connection)
    })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        showAlert(data.message, 'success');
      } else {
        showAlert(`Error: ${data.message}. ${data.error || ''}`, 'danger');
      }
    })
    .catch(error => {
      showAlert(`Network error: ${error.message}`, 'danger');
    });
  }

  // Extract schema from MySQL
  function extractMysqlSchema(editors) {
    const connection = getMysqlConnection();
    const progressBar = document.getElementById('conversionProgress');
    
    progressBar.style.display = 'flex';
    
    fetch('/api/extract-mysql-schema', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(connection)
    })
    .then(response => response.json())
    .then(data => {
      progressBar.style.display = 'none';
      
      if (data.success) {
        currentSchema = data.schema;
        editors.schemaEditor.setValue(JSON.stringify(currentSchema, null, 2));
        currentQueries = '';
        editors.queriesEditor.setValue('');
        
        showAlert('Schema extracted successfully! Proceed to the Convert tab.', 'success');
        activateTab('convert');
      } else {
        showAlert(`Error: ${data.message}. ${data.error || ''}`, 'danger');
      }
    })
    .catch(error => {
      progressBar.style.display = 'none';
      showAlert(`Network error: ${error.message}`, 'danger');
    });
  }

  // Load schema from file upload
  function loadSchemaFromFile(editors) {
    const schemaFile = document.getElementById('schemaFile').files[0];
    const queriesFile = document.getElementById('queriesFile').files[0];
    
    if (!schemaFile) {
      showAlert('Please select a schema file to upload.', 'warning');
      return;
    }
    
    const reader = new FileReader();
    reader.onload = function(e) {
      try {
        currentSchema = JSON.parse(e.target.result);
        editors.schemaEditor.setValue(JSON.stringify(currentSchema, null, 2));
        
        if (queriesFile) {
          const queriesReader = new FileReader();
          queriesReader.onload = function(e) {
            currentQueries = e.target.result;
            editors.queriesEditor.setValue(currentQueries);
            
            showAlert('Schema and queries loaded successfully! Proceed to the Convert tab.', 'success');
            activateTab('convert');
          };
          queriesReader.readAsText(queriesFile);
        } else {
          currentQueries = '';
          editors.queriesEditor.setValue('');
          
          showAlert('Schema loaded successfully! Proceed to the Convert tab.', 'success');
          activateTab('convert');
        }
      } catch (error) {
        showAlert(`Error parsing schema file: ${error.message}`, 'danger');
      }
    };
    reader.readAsText(schemaFile);
  }

  // Load schema from manual entry
  function loadManualSchema(editors) {
    try {
      currentSchema = JSON.parse(editors.manualSchemaEditor.getValue());
      editors.schemaEditor.setValue(JSON.stringify(currentSchema, null, 2));
      
      currentQueries = editors.manualQueriesEditor.getValue();
      editors.queriesEditor.setValue(currentQueries);
      
      showAlert('Schema and queries loaded successfully! Proceed to the Convert tab.', 'success');
      activateTab('convert');
    } catch (error) {
      showAlert(`Error parsing schema JSON: ${error.message}`, 'danger');
    }
  }

  // Convert schema to Cassandra
  function convertSchema(editors) {
    // Make sure editors are read-only again
    editors.schemaEditor.setOption('readOnly', true);
    editors.queriesEditor.setOption('readOnly', true);
    
    // Update current values from potentially edited editors
    try {
      currentSchema = JSON.parse(editors.schemaEditor.getValue());
      currentQueries = editors.queriesEditor.getValue();
    } catch (error) {
      showAlert(`Error parsing schema JSON: ${error.message}`, 'danger');
      return;
    }
    
    const formData = new FormData();
    formData.append('schema', JSON.stringify(currentSchema));
    if (currentQueries) {
      formData.append('queries', currentQueries);
    }
    
    const progressBar = document.getElementById('conversionProgress');
    const statusDiv = document.getElementById('conversionStatus');
    
    progressBar.style.display = 'flex';
    statusDiv.innerHTML = '<div class="alert alert-info">Converting schema... This may take a moment.</div>';
    
    fetch('/api/convert-schema', {
      method: 'POST',
      body: formData
    })
    .then(response => response.json())
    .then(data => {
      progressBar.style.display = 'none';
      
      if (data.success) {
        conversionOutput.cql = data.cqlOutput;
        conversionOutput.summary = data.summaryOutput;
        
        editors.cqlEditor.setValue(data.cqlOutput);
        editors.summaryEditor.setValue(data.summaryOutput);
        
        // Also update the deploy tab
        editors.deployCqlEditor.setValue(data.cqlOutput);
        
        statusDiv.innerHTML = '<div class="alert alert-success">Conversion completed successfully!</div>';
        document.getElementById('downloadCqlBtn').disabled = false;
        document.getElementById('generateReportBtn').disabled = false;
      } else {
        statusDiv.innerHTML = `<div class="alert alert-danger">Error: ${data.message}. ${data.error || ''}</div>`;
      }
    })
    .catch(error => {
      progressBar.style.display = 'none';
      statusDiv.innerHTML = `<div class="alert alert-danger">Network error: ${error.message}</div>`;
    });
  }

  // Download CQL
  function downloadCql() {
    if (!conversionOutput.cql) {
      showAlert('No CQL available to download.', 'warning');
      return;
    }
    
    const blob = new Blob([conversionOutput.cql], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'cassandra_schema.cql';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  // Generate and download schema analysis report
  function generateReport(editors) {
    try {
      // Get current schema and queries
      const schema = JSON.parse(editors.schemaEditor.getValue());
      const queries = editors.queriesEditor.getValue();
      
      const statusDiv = document.getElementById('conversionStatus');
      statusDiv.innerHTML = '<div class="alert alert-info">Generating optimization report... This may take a moment.</div>';
      
      // Create form data
      const formData = new FormData();
      formData.append('schema', JSON.stringify(schema));
      if (queries) {
        formData.append('queries', queries);
      }
      
      // Show progress indicator
      const progressBar = document.getElementById('conversionProgress');
      progressBar.style.display = 'flex';
      
      // Make request to generate report
      fetch('/api/generate-report', {
        method: 'POST',
        body: formData
      })
      .then(response => {
        progressBar.style.display = 'none';
        
        // Check if the response is successful
        if (!response.ok) {
          return response.json().then(data => {
            throw new Error(data.message || 'Failed to generate report');
          });
        }
        
        // It's a PDF, get filename from Content-Disposition header
        let filename = 'cassandra_optimization_report.pdf';
        const disposition = response.headers.get('Content-Disposition');
        if (disposition && disposition.indexOf('attachment') !== -1) {
          const filenameRegex = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/;
          const matches = filenameRegex.exec(disposition);
          if (matches != null && matches[1]) { 
            filename = matches[1].replace(/['"]/g, '');
          }
        }
        
        // Convert response to blob
        return response.blob().then(blob => {
          // Create object URL
          const url = window.URL.createObjectURL(blob);
          
          // Create temp link and click it to download
          const a = document.createElement('a');
          a.href = url;
          a.download = filename;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          window.URL.revokeObjectURL(url);
          
          statusDiv.innerHTML = '<div class="alert alert-success">Report generated and downloaded successfully!</div>';
        });
      })
      .catch(error => {
        progressBar.style.display = 'none';
        statusDiv.innerHTML = `<div class="alert alert-danger">Error generating report: ${error.message}</div>`;
      });
    } catch (error) {
      showAlert(`Error parsing schema: ${error.message}`, 'danger');
    }
  }

  // Test Cassandra connection
  function testCassandraConnection() {
    const connection = getCassandraConnection();
    
    fetch('/api/test-cassandra', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(connection)
    })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        showAlert(data.message, 'success');
      } else {
        showAlert(`Error: ${data.message}. ${data.error || ''}`, 'danger');
      }
    })
    .catch(error => {
      showAlert(`Network error: ${error.message}`, 'danger');
    });
  }

  // Deploy schema to Cassandra
  function deployCassandraSchema() {
    const connection = getCassandraConnection();
    connection.cqlScript = editors.deployCqlEditor.getValue();
    
    if (!connection.cqlScript.trim()) {
      showAlert('No CQL script to deploy.', 'warning');
      return;
    }
    
    const progressBar = document.getElementById('deployProgress');
    const resultsDiv = document.getElementById('deployResults');
    
    progressBar.style.display = 'flex';
    resultsDiv.innerHTML = '';
    
    fetch('/api/deploy-to-cassandra', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(connection)
    })
    .then(response => response.json())
    .then(data => {
      progressBar.style.display = 'none';
      
      if (data.success) {
        resultsDiv.innerHTML = '<div class="alert alert-success mb-3">All statements executed successfully!</div>';
      } else {
        resultsDiv.innerHTML = '<div class="alert alert-warning mb-3">Some statements failed during deployment.</div>';
      }
      
      // Display individual statement results
      const resultsList = document.createElement('div');
      resultsList.className = 'statement-results';
      
      data.results.forEach((result, index) => {
        const item = document.createElement('div');
        item.className = `statement-result ${result.success ? 'success' : 'error'}`;
        
        const stmt = document.createElement('pre');
        stmt.className = 'statement-code';
        stmt.textContent = result.statement;
        
        const status = document.createElement('div');
        status.className = 'statement-status';
        status.innerHTML = result.success 
          ? '<span class="badge bg-success">Success</span>' 
          : `<span class="badge bg-danger">Error</span> ${result.error || ''}`;
        
        item.appendChild(stmt);
        item.appendChild(status);
        resultsList.appendChild(item);
      });
      
      resultsDiv.appendChild(resultsList);
    })
    .catch(error => {
      progressBar.style.display = 'none';
      resultsDiv.innerHTML = `<div class="alert alert-danger">Network error: ${error.message}</div>`;
    });
  }

  // Helper to get MySQL connection details
  function getMysqlConnection() {
    return {
      host: document.getElementById('mysqlHost').value,
      port: document.getElementById('mysqlPort').value,
      database: document.getElementById('mysqlDatabase').value,
      user: document.getElementById('mysqlUser').value,
      password: document.getElementById('mysqlPassword').value
    };
  }

  // Helper to get Cassandra connection details
  function getCassandraConnection() {
    return {
      contactPoints: document.getElementById('cassandraContactPoints').value,
      localDataCenter: document.getElementById('cassandraDataCenter').value,
      keyspace: document.getElementById('cassandraKeyspace').value,
      username: document.getElementById('cassandraUser').value,
      password: document.getElementById('cassandraPassword').value
    };
  }

  // Helper to show alerts
  function showAlert(message, type) {
    const template = document.getElementById('alertTemplate');
    const alert = template.content.cloneNode(true);
    
    const alertElement = alert.querySelector('.alert');
    alertElement.classList.add(`alert-${type}`);
    
    const messageElement = alert.querySelector('.alert-message');
    messageElement.textContent = message;
    
    const container = document.getElementById('conversionStatus');
    container.innerHTML = '';
    container.appendChild(alert);
  }
});