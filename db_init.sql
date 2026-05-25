-- Create database and add sample candidates
CREATE DATABASE IF NOT EXISTS voting_system;
USE voting_system;

-- Tables will be created automatically by the Flask app's init_db(), but you can create candidates now:
CREATE TABLE IF NOT EXISTS candidates (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  party VARCHAR(100) NOT NULL,
  party_color VARCHAR(7) NOT NULL,
  image VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS votes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  voter_id INT NOT NULL,
  candidate_id INT NOT NULL,
  vote_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (voter_id) REFERENCES voters(id),
  FOREIGN KEY (candidate_id) REFERENCES candidates(id)
);

INSERT INTO candidates (name, party, party_color, image) VALUES
('Chiroma', 'Party Blue', '#004085', 'chiroma.jpg'),
('Kamto', 'Party Red', '#dc3545', 'Kamto.jpg'),
('Papi P', 'Party Green', '#28a745', 'papiP.jpg')
ON DUPLICATE KEY UPDATE name=VALUES(name);
