--
-- PostgreSQL database dump
--

\restrict 0eze3E2rKMwTI6mBccHPVCrZu8wrCgvHxTwRERPt5qmRilEYTyqexvESLZnFgp8

-- Dumped from database version 18.0
-- Dumped by pg_dump version 18.0

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: smart_spa; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA smart_spa;


ALTER SCHEMA smart_spa OWNER TO postgres;

--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA smart_spa;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


--
-- Name: book_appointment(bigint, bigint, bigint, bigint, bigint); Type: FUNCTION; Schema: smart_spa; Owner: postgres
--

CREATE FUNCTION smart_spa.book_appointment(p_client bigint, p_salon bigint, p_master bigint, p_service bigint, p_slot bigint) RETURNS bigint
    LANGUAGE plpgsql
    AS $$
DECLARE v_id BIGINT;
DECLARE v_start TIMESTAMPTZ; DECLARE v_end TIMESTAMPTZ;
BEGIN
  -- Master belongs to the salon and is active
  IF NOT EXISTS (
    SELECT 1 FROM smart_spa.masters m WHERE m.id = p_master AND m.salon_id = p_salon AND m.active
  ) THEN
    RAISE EXCEPTION 'Ошибка: мастер не найден в салоне.';
  END IF;

  -- Salon actually offers this service
  IF NOT EXISTS (
    SELECT 1 FROM smart_spa.salon_services ss WHERE ss.salon_id = p_salon AND ss.service_id = p_service
  ) THEN
    RAISE EXCEPTION 'Ошибка: услуга недоступна в салоне.';
  END IF;

  -- Master performs this service
  IF NOT EXISTS (
    SELECT 1 FROM smart_spa.master_services ms WHERE ms.master_id = p_master AND ms.service_id = p_service
  ) THEN
    RAISE EXCEPTION 'Ошибка: мастер не выполняет выбранную услугу.';
  END IF;

  -- Slot belongs to the master and is in the future
  SELECT start_ts, end_ts INTO v_start, v_end
  FROM smart_spa.schedule_slots s
  WHERE s.id = p_slot AND s.master_id = p_master
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Ошибка: слот не найден или не принадлежит мастеру.';
  END IF;
  IF v_start < now() THEN
    RAISE EXCEPTION 'Ошибка: нельзя бронировать прошедший слот.';
  END IF;

  -- Slot is still free
  IF EXISTS (SELECT 1 FROM smart_spa.schedule_slots WHERE id = p_slot AND is_booked) THEN
    RAISE EXCEPTION 'Ошибка: слот уже занят.';
  END IF;

  -- Client has no overlapping appointments
  IF EXISTS (
    SELECT 1
    FROM smart_spa.appointments a
    JOIN smart_spa.schedule_slots s2 ON s2.id = a.slot_id
    WHERE a.client_id = p_client
      AND a.status IN ('ожидает подтверждения','подтверждена')
      AND tstzrange(s2.start_ts, s2.end_ts, '[)') && tstzrange(v_start, v_end, '[)')
  ) THEN
    RAISE EXCEPTION 'Ошибка: у клиента уже есть запись в это время.';
  END IF;

  INSERT INTO smart_spa.appointments (client_id, salon_id, master_id, service_id, slot_id, status)
  VALUES (p_client, p_salon, p_master, p_service, p_slot, 'ожидает подтверждения')
  RETURNING id INTO v_id;

  RETURN v_id;
END;
$$;


ALTER FUNCTION smart_spa.book_appointment(p_client bigint, p_salon bigint, p_master bigint, p_service bigint, p_slot bigint) OWNER TO postgres;

--
-- Name: cancel_appointment(bigint); Type: FUNCTION; Schema: smart_spa; Owner: postgres
--

CREATE FUNCTION smart_spa.cancel_appointment(p_id bigint) RETURNS void
    LANGUAGE plpgsql
    AS $$
DECLARE v_slot BIGINT; DECLARE v_start TIMESTAMPTZ;
BEGIN
  SELECT slot_id, s.start_ts INTO v_slot, v_start
  FROM smart_spa.appointments a
  JOIN smart_spa.schedule_slots s ON s.id = a.slot_id
  WHERE a.id = p_id AND a.status IN ('ожидает подтверждения','подтверждена')
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE NOTICE 'Запись не найдена или уже отменена/завершена.';
    RETURN;
  END IF;

  IF v_start <= now() THEN
    RAISE EXCEPTION 'Нельзя отменить запись, время которой уже прошло или наступило.';
  END IF;

  UPDATE smart_spa.appointments SET status = 'отменена' WHERE id = p_id;
END;
$$;


ALTER FUNCTION smart_spa.cancel_appointment(p_id bigint) OWNER TO postgres;

--
-- Name: check_review_after_visit(); Type: FUNCTION; Schema: smart_spa; Owner: postgres
--

CREATE FUNCTION smart_spa.check_review_after_visit() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM appointments a
    WHERE a.id = NEW.appointment_id
      AND a.client_id = NEW.client_id
      AND a.salon_id  = NEW.salon_id
      AND a.status    = 'завершена'
  ) THEN
    RAISE EXCEPTION 'Ошибка: отзыв можно оставить только после завершённого визита.';
  END IF;
  RETURN NEW;
END;
$$;


ALTER FUNCTION smart_spa.check_review_after_visit() OWNER TO postgres;

--
-- Name: check_slot_overlap(); Type: FUNCTION; Schema: smart_spa; Owner: postgres
--

CREATE FUNCTION smart_spa.check_slot_overlap() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM schedule_slots s
    WHERE s.master_id = NEW.master_id
      AND tstzrange(s.start_ts, s.end_ts, '[)') && tstzrange(NEW.start_ts, NEW.end_ts, '[)')
      AND s.id <> COALESCE(NEW.id, -1)
  ) THEN
    RAISE EXCEPTION 'Ошибка: слот пересекается с уже существующим временем мастера %', NEW.master_id;
  END IF;
  RETURN NEW;
END;
$$;


ALTER FUNCTION smart_spa.check_slot_overlap() OWNER TO postgres;

--
-- Name: sync_slot_booked(); Type: FUNCTION; Schema: smart_spa; Owner: postgres
--

CREATE FUNCTION smart_spa.sync_slot_booked() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    UPDATE smart_spa.schedule_slots SET is_booked = TRUE WHERE id = NEW.slot_id;
  ELSIF TG_OP = 'DELETE' THEN
    UPDATE smart_spa.schedule_slots SET is_booked = FALSE WHERE id = OLD.slot_id;
  ELSIF TG_OP = 'UPDATE' AND NEW.slot_id <> OLD.slot_id THEN
    UPDATE smart_spa.schedule_slots SET is_booked = FALSE WHERE id = OLD.slot_id;
    UPDATE smart_spa.schedule_slots SET is_booked = TRUE  WHERE id = NEW.slot_id;
  END IF;
  RETURN NULL;
END; $$;


ALTER FUNCTION smart_spa.sync_slot_booked() OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: appointments; Type: TABLE; Schema: smart_spa; Owner: postgres
--

CREATE TABLE smart_spa.appointments (
    id bigint NOT NULL,
    client_id bigint NOT NULL,
    salon_id bigint NOT NULL,
    master_id bigint NOT NULL,
    service_id bigint NOT NULL,
    slot_id bigint NOT NULL,
    status character varying(30) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT appointments_status_check CHECK (((status)::text = ANY ((ARRAY['ожидает подтверждения'::character varying, 'подтверждена'::character varying, 'отменена'::character varying, 'завершена'::character varying])::text[])))
);


ALTER TABLE smart_spa.appointments OWNER TO postgres;

--
-- Name: appointments_id_seq; Type: SEQUENCE; Schema: smart_spa; Owner: postgres
--

CREATE SEQUENCE smart_spa.appointments_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE smart_spa.appointments_id_seq OWNER TO postgres;

--
-- Name: appointments_id_seq; Type: SEQUENCE OWNED BY; Schema: smart_spa; Owner: postgres
--

ALTER SEQUENCE smart_spa.appointments_id_seq OWNED BY smart_spa.appointments.id;


--
-- Name: master_services; Type: TABLE; Schema: smart_spa; Owner: postgres
--

CREATE TABLE smart_spa.master_services (
    master_id bigint NOT NULL,
    service_id bigint NOT NULL
);


ALTER TABLE smart_spa.master_services OWNER TO postgres;

--
-- Name: masters; Type: TABLE; Schema: smart_spa; Owner: postgres
--

CREATE TABLE smart_spa.masters (
    id bigint NOT NULL,
    salon_id bigint NOT NULL,
    full_name character varying(200) NOT NULL,
    specialization character varying(200),
    active boolean DEFAULT true NOT NULL
);


ALTER TABLE smart_spa.masters OWNER TO postgres;

--
-- Name: masters_id_seq; Type: SEQUENCE; Schema: smart_spa; Owner: postgres
--

CREATE SEQUENCE smart_spa.masters_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE smart_spa.masters_id_seq OWNER TO postgres;

--
-- Name: masters_id_seq; Type: SEQUENCE OWNED BY; Schema: smart_spa; Owner: postgres
--

ALTER SEQUENCE smart_spa.masters_id_seq OWNED BY smart_spa.masters.id;


--
-- Name: reviews; Type: TABLE; Schema: smart_spa; Owner: postgres
--

CREATE TABLE smart_spa.reviews (
    id bigint NOT NULL,
    salon_id bigint NOT NULL,
    client_id bigint,
    appointment_id bigint,
    rating smallint NOT NULL,
    comment text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT reviews_rating_check CHECK (((rating >= 1) AND (rating <= 5)))
);


ALTER TABLE smart_spa.reviews OWNER TO postgres;

--
-- Name: reviews_id_seq; Type: SEQUENCE; Schema: smart_spa; Owner: postgres
--

CREATE SEQUENCE smart_spa.reviews_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE smart_spa.reviews_id_seq OWNER TO postgres;

--
-- Name: reviews_id_seq; Type: SEQUENCE OWNED BY; Schema: smart_spa; Owner: postgres
--

ALTER SEQUENCE smart_spa.reviews_id_seq OWNED BY smart_spa.reviews.id;


--
-- Name: roles; Type: TABLE; Schema: smart_spa; Owner: postgres
--

CREATE TABLE smart_spa.roles (
    id integer NOT NULL,
    code character varying(32) NOT NULL,
    name character varying(128) NOT NULL
);


ALTER TABLE smart_spa.roles OWNER TO postgres;

--
-- Name: roles_id_seq; Type: SEQUENCE; Schema: smart_spa; Owner: postgres
--

CREATE SEQUENCE smart_spa.roles_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE smart_spa.roles_id_seq OWNER TO postgres;

--
-- Name: roles_id_seq; Type: SEQUENCE OWNED BY; Schema: smart_spa; Owner: postgres
--

ALTER SEQUENCE smart_spa.roles_id_seq OWNED BY smart_spa.roles.id;


--
-- Name: salon_services; Type: TABLE; Schema: smart_spa; Owner: postgres
--

CREATE TABLE smart_spa.salon_services (
    salon_id bigint NOT NULL,
    service_id bigint NOT NULL,
    price numeric(10,2),
    CONSTRAINT salon_services_price_check CHECK ((price >= (0)::numeric))
);


ALTER TABLE smart_spa.salon_services OWNER TO postgres;

--
-- Name: salon_users; Type: TABLE; Schema: smart_spa; Owner: postgres
--

CREATE TABLE smart_spa.salon_users (
    user_id bigint NOT NULL,
    salon_id bigint NOT NULL
);


ALTER TABLE smart_spa.salon_users OWNER TO postgres;

--
-- Name: salons; Type: TABLE; Schema: smart_spa; Owner: postgres
--

CREATE TABLE smart_spa.salons (
    id bigint NOT NULL,
    name character varying(200) NOT NULL,
    city character varying(120) NOT NULL,
    address character varying(300) NOT NULL,
    phone character varying(32),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE smart_spa.salons OWNER TO postgres;

--
-- Name: salons_id_seq; Type: SEQUENCE; Schema: smart_spa; Owner: postgres
--

CREATE SEQUENCE smart_spa.salons_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE smart_spa.salons_id_seq OWNER TO postgres;

--
-- Name: salons_id_seq; Type: SEQUENCE OWNED BY; Schema: smart_spa; Owner: postgres
--

ALTER SEQUENCE smart_spa.salons_id_seq OWNED BY smart_spa.salons.id;


--
-- Name: schedule_slots; Type: TABLE; Schema: smart_spa; Owner: postgres
--

CREATE TABLE smart_spa.schedule_slots (
    id bigint NOT NULL,
    master_id bigint NOT NULL,
    start_ts timestamp with time zone NOT NULL,
    end_ts timestamp with time zone NOT NULL,
    is_booked boolean DEFAULT false NOT NULL,
    CONSTRAINT schedule_slots_check CHECK ((end_ts > start_ts))
);


ALTER TABLE smart_spa.schedule_slots OWNER TO postgres;

--
-- Name: schedule_slots_id_seq; Type: SEQUENCE; Schema: smart_spa; Owner: postgres
--

CREATE SEQUENCE smart_spa.schedule_slots_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE smart_spa.schedule_slots_id_seq OWNER TO postgres;

--
-- Name: schedule_slots_id_seq; Type: SEQUENCE OWNED BY; Schema: smart_spa; Owner: postgres
--

ALTER SEQUENCE smart_spa.schedule_slots_id_seq OWNED BY smart_spa.schedule_slots.id;


--
-- Name: services; Type: TABLE; Schema: smart_spa; Owner: postgres
--

CREATE TABLE smart_spa.services (
    id bigint NOT NULL,
    name character varying(200) NOT NULL,
    description text,
    base_price numeric(10,2) NOT NULL,
    duration_min integer NOT NULL,
    CONSTRAINT services_base_price_check CHECK ((base_price >= (0)::numeric)),
    CONSTRAINT services_duration_min_check CHECK (((duration_min >= 15) AND (duration_min <= 480)))
);


ALTER TABLE smart_spa.services OWNER TO postgres;

--
-- Name: services_id_seq; Type: SEQUENCE; Schema: smart_spa; Owner: postgres
--

CREATE SEQUENCE smart_spa.services_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE smart_spa.services_id_seq OWNER TO postgres;

--
-- Name: services_id_seq; Type: SEQUENCE OWNED BY; Schema: smart_spa; Owner: postgres
--

ALTER SEQUENCE smart_spa.services_id_seq OWNED BY smart_spa.services.id;


--
-- Name: users; Type: TABLE; Schema: smart_spa; Owner: postgres
--

CREATE TABLE smart_spa.users (
    id bigint NOT NULL,
    full_name character varying(200) NOT NULL,
    phone character varying(32) NOT NULL,
    email character varying(200),
    password_hash text NOT NULL,
    role_id integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE smart_spa.users OWNER TO postgres;

--
-- Name: users_id_seq; Type: SEQUENCE; Schema: smart_spa; Owner: postgres
--

CREATE SEQUENCE smart_spa.users_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE smart_spa.users_id_seq OWNER TO postgres;

--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: smart_spa; Owner: postgres
--

ALTER SEQUENCE smart_spa.users_id_seq OWNED BY smart_spa.users.id;


--
-- Name: appointments id; Type: DEFAULT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.appointments ALTER COLUMN id SET DEFAULT nextval('smart_spa.appointments_id_seq'::regclass);


--
-- Name: masters id; Type: DEFAULT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.masters ALTER COLUMN id SET DEFAULT nextval('smart_spa.masters_id_seq'::regclass);


--
-- Name: reviews id; Type: DEFAULT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.reviews ALTER COLUMN id SET DEFAULT nextval('smart_spa.reviews_id_seq'::regclass);


--
-- Name: roles id; Type: DEFAULT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.roles ALTER COLUMN id SET DEFAULT nextval('smart_spa.roles_id_seq'::regclass);


--
-- Name: salons id; Type: DEFAULT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.salons ALTER COLUMN id SET DEFAULT nextval('smart_spa.salons_id_seq'::regclass);


--
-- Name: schedule_slots id; Type: DEFAULT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.schedule_slots ALTER COLUMN id SET DEFAULT nextval('smart_spa.schedule_slots_id_seq'::regclass);


--
-- Name: services id; Type: DEFAULT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.services ALTER COLUMN id SET DEFAULT nextval('smart_spa.services_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.users ALTER COLUMN id SET DEFAULT nextval('smart_spa.users_id_seq'::regclass);


--
-- Name: appointments appointments_pkey; Type: CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.appointments
    ADD CONSTRAINT appointments_pkey PRIMARY KEY (id);


--
-- Name: appointments appointments_slot_id_key; Type: CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.appointments
    ADD CONSTRAINT appointments_slot_id_key UNIQUE (slot_id);


--
-- Name: master_services master_services_pkey; Type: CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.master_services
    ADD CONSTRAINT master_services_pkey PRIMARY KEY (master_id, service_id);


--
-- Name: masters masters_pkey; Type: CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.masters
    ADD CONSTRAINT masters_pkey PRIMARY KEY (id);


--
-- Name: reviews reviews_appointment_id_key; Type: CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.reviews
    ADD CONSTRAINT reviews_appointment_id_key UNIQUE (appointment_id);


--
-- Name: reviews reviews_pkey; Type: CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.reviews
    ADD CONSTRAINT reviews_pkey PRIMARY KEY (id);


--
-- Name: roles roles_code_key; Type: CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.roles
    ADD CONSTRAINT roles_code_key UNIQUE (code);


--
-- Name: roles roles_pkey; Type: CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.roles
    ADD CONSTRAINT roles_pkey PRIMARY KEY (id);


--
-- Name: salon_services salon_services_pkey; Type: CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.salon_services
    ADD CONSTRAINT salon_services_pkey PRIMARY KEY (salon_id, service_id);


--
-- Name: salon_users salon_users_pkey; Type: CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.salon_users
    ADD CONSTRAINT salon_users_pkey PRIMARY KEY (user_id, salon_id);


--
-- Name: salons salons_pkey; Type: CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.salons
    ADD CONSTRAINT salons_pkey PRIMARY KEY (id);


--
-- Name: schedule_slots schedule_slots_pkey; Type: CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.schedule_slots
    ADD CONSTRAINT schedule_slots_pkey PRIMARY KEY (id);


--
-- Name: services services_pkey; Type: CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.services
    ADD CONSTRAINT services_pkey PRIMARY KEY (id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_phone_key; Type: CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.users
    ADD CONSTRAINT users_phone_key UNIQUE (phone);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: idx_appointments_client; Type: INDEX; Schema: smart_spa; Owner: postgres
--

CREATE INDEX idx_appointments_client ON smart_spa.appointments USING btree (client_id);


--
-- Name: idx_master_services_service; Type: INDEX; Schema: smart_spa; Owner: postgres
--

CREATE INDEX idx_master_services_service ON smart_spa.master_services USING btree (service_id);


--
-- Name: idx_masters_salon_active; Type: INDEX; Schema: smart_spa; Owner: postgres
--

CREATE INDEX idx_masters_salon_active ON smart_spa.masters USING btree (salon_id, active);


--
-- Name: idx_reviews_salon_created; Type: INDEX; Schema: smart_spa; Owner: postgres
--

CREATE INDEX idx_reviews_salon_created ON smart_spa.reviews USING btree (salon_id, created_at DESC);


--
-- Name: idx_salon_users_user; Type: INDEX; Schema: smart_spa; Owner: postgres
--

CREATE INDEX idx_salon_users_user ON smart_spa.salon_users USING btree (user_id);


--
-- Name: idx_schedule_master_start; Type: INDEX; Schema: smart_spa; Owner: postgres
--

CREATE INDEX idx_schedule_master_start ON smart_spa.schedule_slots USING btree (master_id, start_ts);


--
-- Name: reviews trg_check_review_after_visit; Type: TRIGGER; Schema: smart_spa; Owner: postgres
--

CREATE TRIGGER trg_check_review_after_visit BEFORE INSERT OR UPDATE ON smart_spa.reviews FOR EACH ROW EXECUTE FUNCTION smart_spa.check_review_after_visit();


--
-- Name: schedule_slots trg_check_slot_overlap; Type: TRIGGER; Schema: smart_spa; Owner: postgres
--

CREATE TRIGGER trg_check_slot_overlap BEFORE INSERT OR UPDATE ON smart_spa.schedule_slots FOR EACH ROW EXECUTE FUNCTION smart_spa.check_slot_overlap();


--
-- Name: appointments trg_sync_slot_booked; Type: TRIGGER; Schema: smart_spa; Owner: postgres
--

CREATE TRIGGER trg_sync_slot_booked AFTER INSERT OR DELETE OR UPDATE ON smart_spa.appointments FOR EACH ROW EXECUTE FUNCTION smart_spa.sync_slot_booked();


--
-- Name: appointments appointments_client_id_fkey; Type: FK CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.appointments
    ADD CONSTRAINT appointments_client_id_fkey FOREIGN KEY (client_id) REFERENCES smart_spa.users(id) ON DELETE CASCADE;


--
-- Name: appointments appointments_master_id_fkey; Type: FK CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.appointments
    ADD CONSTRAINT appointments_master_id_fkey FOREIGN KEY (master_id) REFERENCES smart_spa.masters(id) ON DELETE RESTRICT;


--
-- Name: appointments appointments_salon_id_fkey; Type: FK CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.appointments
    ADD CONSTRAINT appointments_salon_id_fkey FOREIGN KEY (salon_id) REFERENCES smart_spa.salons(id) ON DELETE RESTRICT;


--
-- Name: appointments appointments_service_id_fkey; Type: FK CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.appointments
    ADD CONSTRAINT appointments_service_id_fkey FOREIGN KEY (service_id) REFERENCES smart_spa.services(id) ON DELETE RESTRICT;


--
-- Name: appointments appointments_slot_id_fkey; Type: FK CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.appointments
    ADD CONSTRAINT appointments_slot_id_fkey FOREIGN KEY (slot_id) REFERENCES smart_spa.schedule_slots(id) ON DELETE RESTRICT;


--
-- Name: master_services master_services_master_id_fkey; Type: FK CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.master_services
    ADD CONSTRAINT master_services_master_id_fkey FOREIGN KEY (master_id) REFERENCES smart_spa.masters(id) ON DELETE CASCADE;


--
-- Name: master_services master_services_service_id_fkey; Type: FK CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.master_services
    ADD CONSTRAINT master_services_service_id_fkey FOREIGN KEY (service_id) REFERENCES smart_spa.services(id) ON DELETE CASCADE;


--
-- Name: masters masters_salon_id_fkey; Type: FK CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.masters
    ADD CONSTRAINT masters_salon_id_fkey FOREIGN KEY (salon_id) REFERENCES smart_spa.salons(id) ON DELETE CASCADE;


--
-- Name: reviews reviews_appointment_id_fkey; Type: FK CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.reviews
    ADD CONSTRAINT reviews_appointment_id_fkey FOREIGN KEY (appointment_id) REFERENCES smart_spa.appointments(id) ON DELETE SET NULL;


--
-- Name: reviews reviews_client_id_fkey; Type: FK CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.reviews
    ADD CONSTRAINT reviews_client_id_fkey FOREIGN KEY (client_id) REFERENCES smart_spa.users(id) ON DELETE SET NULL;


--
-- Name: reviews reviews_salon_id_fkey; Type: FK CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.reviews
    ADD CONSTRAINT reviews_salon_id_fkey FOREIGN KEY (salon_id) REFERENCES smart_spa.salons(id) ON DELETE CASCADE;


--
-- Name: salon_services salon_services_salon_id_fkey; Type: FK CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.salon_services
    ADD CONSTRAINT salon_services_salon_id_fkey FOREIGN KEY (salon_id) REFERENCES smart_spa.salons(id) ON DELETE CASCADE;


--
-- Name: salon_services salon_services_service_id_fkey; Type: FK CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.salon_services
    ADD CONSTRAINT salon_services_service_id_fkey FOREIGN KEY (service_id) REFERENCES smart_spa.services(id) ON DELETE CASCADE;


--
-- Name: salon_users salon_users_salon_id_fkey; Type: FK CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.salon_users
    ADD CONSTRAINT salon_users_salon_id_fkey FOREIGN KEY (salon_id) REFERENCES smart_spa.salons(id) ON DELETE CASCADE;


--
-- Name: salon_users salon_users_user_id_fkey; Type: FK CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.salon_users
    ADD CONSTRAINT salon_users_user_id_fkey FOREIGN KEY (user_id) REFERENCES smart_spa.users(id) ON DELETE CASCADE;


--
-- Name: schedule_slots schedule_slots_master_id_fkey; Type: FK CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.schedule_slots
    ADD CONSTRAINT schedule_slots_master_id_fkey FOREIGN KEY (master_id) REFERENCES smart_spa.masters(id) ON DELETE CASCADE;


--
-- Name: users users_role_id_fkey; Type: FK CONSTRAINT; Schema: smart_spa; Owner: postgres
--

ALTER TABLE ONLY smart_spa.users
    ADD CONSTRAINT users_role_id_fkey FOREIGN KEY (role_id) REFERENCES smart_spa.roles(id);


--
-- PostgreSQL database dump complete
--

\unrestrict 0eze3E2rKMwTI6mBccHPVCrZu8wrCgvHxTwRERPt5qmRilEYTyqexvESLZnFgp8

