-- Supabase Database Schema for Job Board Aggregator
-- Run this in Supabase SQL Editor

-- Table 1: Companies (replaces companies.csv)
CREATE TABLE companies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    api_url TEXT NOT NULL,
    last_fetch_time TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Table 2: System Configuration (replaces parts of last_fetch.json)
CREATE TABLE system_config (
    id SERIAL PRIMARY KEY,
    config_key VARCHAR(100) UNIQUE NOT NULL,
    config_value TEXT NOT NULL,
    description TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_companies_name ON companies(name);
CREATE INDEX idx_companies_last_fetch ON companies(last_fetch_time);
CREATE INDEX idx_companies_active ON companies(is_active);
CREATE INDEX idx_system_config_key ON system_config(config_key);

-- Insert default start date from current last_fetch.json
INSERT INTO system_config (config_key, config_value, description) 
VALUES ('default_start_date', '2025-06-18T00:00:00+00:00', 'Default start date for fetching jobs when no company-specific timestamp exists');

-- Function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers to auto-update timestamps
CREATE TRIGGER update_companies_updated_at BEFORE UPDATE ON companies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_system_config_updated_at BEFORE UPDATE ON system_config
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Enable Row Level Security (optional - uncomment if needed)
-- ALTER TABLE companies ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE system_config ENABLE ROW LEVEL SECURITY;

-- Create policies for authenticated access (optional - uncomment if needed)
-- CREATE POLICY "Allow authenticated users to read companies" ON companies
--     FOR SELECT USING (auth.role() = 'authenticated');
    
-- CREATE POLICY "Allow authenticated users to modify companies" ON companies
--     FOR ALL USING (auth.role() = 'authenticated');

-- CREATE POLICY "Allow authenticated users to read system_config" ON system_config
--     FOR SELECT USING (auth.role() = 'authenticated');
    
-- CREATE POLICY "Allow authenticated users to modify system_config" ON system_config
--     FOR ALL USING (auth.role() = 'authenticated');
