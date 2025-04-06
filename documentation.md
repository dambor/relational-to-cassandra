# Relational to Cassandra Converter - Project Setup

## Project Structure

```
relational-to-cassandra/
├── public/                  # Static frontend files
│   ├── css/
│   │   └── styles.css       # CSS for the frontend
│   ├── js/
│   │   └── app.js           # Frontend JavaScript
│   └── index.html           # Main HTML file
├── rel_to_cassandra.py      # Python conversion script
├── app.js                   # Backend Express server
├── package.json             # Node.js dependencies
└── README.md                # Project documentation
```

## Installation Instructions

### Prerequisites

1. Node.js (v14+)
2. Python 3.7+
3. MySQL (or another relational database)
4. Apache Cassandra

### Setup Steps

1. **Clone the repository:**

   ```bash
   git clone <repository-url>
   cd relational-to-cassandra
   ```

2. **Install Node.js dependencies:**

   ```bash
   npm install
   ```

3. **Install Python dependencies:**

   ```bash
   pip install mysql-connector-python cassandra-driver
   ```

4. **Create the directory structure:**

   ```bash
   mkdir -p public/css public/js
   ```

5. **Copy files to their appropriate locations:**
   - Copy the backend `app.js` to the root directory
   - Copy the frontend JavaScript to `public/js/app.js`
   - Copy the CSS to `public/css/styles.css`
   - Copy the HTML to `public/index.html`
   - Copy the Python script to `rel_to_cassandra.py`

6. **Make the Python script executable:**

   ```bash
   chmod +x rel_to_cassandra.py
   ```

7. **Start the application:**

   ```bash
   node app.js
   ```

8. **Access the web interface:**
   
   Open your browser and navigate to `http://localhost:3000`

## Using the Application

### Step 1: Import Schema

There are three ways to import your relational schema:

1. **From MySQL Database:**
   - Enter the connection details for your MySQL database
   - Test the connection to make sure it works
   - Click "Extract Schema" to import the database structure

2. **Upload Schema File:**
   - Prepare a JSON file that describes your relational schema
   - Optionally prepare a text file with common query patterns
   - Upload these files and click "Load Schema"

3. **Manual Entry:**
   - Use the JSON editor to define your schema
   - Optionally add common query patterns
   - Click "Load Schema" when done

### Step 2: Convert Schema

1. Review the imported schema and make any needed adjustments
2. Click "Convert to Cassandra" to run the conversion process
3. Review the generated CQL and conversion summary
4. Download the CQL file if needed

### Step 3: Deploy to Cassandra

1. Enter your Cassandra connection details
2. Test the connection to make sure it works
3. Review the CQL code and make any final adjustments
4. Click "Deploy Schema" to create the tables in Cassandra
5. Review the deployment results

## Troubleshooting

### Common Issues

- **MySQL Connection Failures:**
  - Verify that the MySQL server is running
  - Check that the username and password are correct
  - Ensure the database exists and the user has access to it

- **Cassandra Connection Failures:**
  - Verify that Cassandra is running
  - Make sure the contact points and data center are correct
  - Check that the keyspace exists or that your user has permission to create it

- **Conversion Failures:**
  - Ensure your schema JSON is properly formatted
  - Check the server logs for Python error messages
  - Verify that the Python script has execution permissions

## License

This project is licensed under the MIT License - see the LICENSE file for details.
