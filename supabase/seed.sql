-- =====================================================================
-- OPTIONAL demo data for Supabase. Run AFTER schema.sql in the SQL Editor.
-- All companies are fictional. Dates are relative to "today" when you run it.
-- (Alternative: with the backend running, click "Load demo data" in the app.)
-- =====================================================================
insert into public.job_applications
    (company_name, job_title, job_description, job_url, application_date, status, follow_up_date, notes, resume_version, location)
values
 ('Nimbus Analytics','Junior Data Analyst','Analyse customer data with SQL and Python; build dashboards in Power BI. 0-2 years experience.','https://example.com/jobs/nimbus-data-analyst', current_date - 12,'Applied', current_date - 2,'Referred by a college senior.','v2-data','Pune'),
 ('Brightwave Systems','Embedded Software Engineer','Write C/C++ firmware for ARM Cortex-M devices. Knowledge of RTOS, I2C, SPI, UART. 1-3 years.','https://example.com/jobs/brightwave-embedded', current_date - 20,'Interview', current_date + 2,'Technical round on Friday.','v3-embedded','Bengaluru'),
 ('Quantora Labs','Python Developer Intern','Build REST APIs with FastAPI and PostgreSQL. Great for final-year students.','https://example.com/jobs/quantora-intern', null,'Saved', current_date + 5,'Deadline next week.','v1-general','Remote'),
 ('Greenfield Robotics','IoT Engineer','Design sensor networks using ESP32 and MQTT. Cloud experience is a plus.','https://example.com/jobs/greenfield-iot', current_date - 30,'Offer', null,'Offer received - decide by month end.','v3-embedded','Hyderabad'),
 ('Lumen Telecom','Network Engineer Trainee','Support 4G/5G RAN deployment; knowledge of signal processing and networking.','https://example.com/jobs/lumen-trainee', current_date - 25,'Rejected', null,'Rejected after aptitude round.','v1-general','Mumbai'),
 ('Orbit Payments','Backend Engineer','Build payment APIs in Python. 2+ years experience with Django or FastAPI.','https://example.com/jobs/orbit-backend', current_date - 8,'Assessment', current_date + 1,'Online coding test link received.','v2-data','Pune'),
 ('Vertex Embedded','Firmware Intern','Assist with PCB bring-up and firmware testing. Hands-on lab experience required.','https://example.com/jobs/vertex-intern', current_date - 15,'Withdrawn', null,'Withdrew - accepted another offer.','v3-embedded','Chennai');

-- Matching history rows (one "created" entry per application)
insert into public.application_history (application_id, old_status, new_status, note)
select id, null, status, 'Application created' from public.job_applications;
