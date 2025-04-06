# Relational to Cassandra Converter

A web-based tool that converts relational database schemas to optimized Cassandra database schemas. This application allows you to extract schemas directly from MySQL databases or import them from files, then convert and deploy them to Cassandra.

## Features

- **Extract Schema**: Connect directly to MySQL databases to extract schema information
- **Smart Conversion**: Optimizes for Cassandra's distributed architecture with intelligent denormalization
- **Deploy**: Deploy the converted schema directly to a Cassandra database
- **User-Friendly Interface**: Step-by-step process with interactive schema editors

## Prerequisites

- Node.js v14 or newer
- Python 3.7 or newer
- MySQL server (for extraction)
- Apache Cassandra (for deployment)

## Installation

1. **Clone the repository**
   ```
   git clone https://github.com/yourusername/relational-to-cassandra.git
   cd relational-to-cassandra
   ```

2. **Install Node.js dependencies**
   ```
   npm install
   ```

3. **Install Python dependencies**
   ```
   pip install mysql-connector-python cassandra-driver
   ```

4. **Make the Python script executable**
   ```
   chmod +x rel_to_cassandra.py
   ```

## Quick Start

1. **Start the server**
   ```
   node app.js
   ```

2. **Access the web interface**
   
   Open your browser and navigate to: http://localhost:3000

3. **Import schema**
   - Connect to a MySQL database
   - Upload a JSON schema file (example provided in `examples/complex-ecommerce-schema.json`)
   - Or use the manual schema editor

4. **Convert schema**
   - Review and optionally edit the imported schema
   - Click "Convert to Cassandra" to generate the CQL

5. **Deploy to Cassandra**
   - Enter your Cassandra connection details
   - Review the generated CQL
   - Deploy directly to your Cassandra cluster

## Example Schema

An example e-commerce schema is included in the `examples` directory. Use it to test the conversion process:

```
examples/complex-ecommerce-schema.json
examples/ecommerce-queries.txt
```

## Troubleshooting

- **MySQL connection issues**: Verify your MySQL server is running and credentials are correct
- **Conversion errors**: Check that your schema is valid JSON
- **Deployment failures**: Ensure your Cassandra cluster is running and accessible

## License

MIT

---

Created with ❤️ for NoSQL enthusiasts