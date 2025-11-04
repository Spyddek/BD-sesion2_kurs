--
-- PostgreSQL database dump
--

\restrict T9aZownHAUEgUAUgaHfQq8p55vs7hcTmW8vHtmHWcSr8sN3UtNRfssY61ivG3UL

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
BEGIN
  PERFORM 1 FROM schedule_slots WHERE id = p_slot AND master_id = p_master FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Ошибка: слот не найден или не принадлежит мастеру.';
  END IF;

  IF EXISTS (SELECT 1 FROM schedule_slots WHERE id = p_slot AND is_booked) THEN
    RAISE EXCEPTION 'Ошибка: слот уже занят.';
  END IF;

  UPDATE schedule_slots SET is_booked = TRUE WHERE id = p_slot;

  INSERT INTO appointments(client_id, salon_id, master_id, service_id, slot_id, status)
  VALUES (p_client, p_salon, p_master, p_service, p_slot, 'подтверждена')
  RETURNING id INTO v_id;

  RAISE NOTICE 'Запись создана №%', v_id;
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
DECLARE v_slot BIGINT;
BEGIN
  UPDATE appointments
     SET status = 'отменена'
   WHERE id = p_id AND status IN ('ожидает подтверждения','подтверждена')
  RETURNING slot_id INTO v_slot;

  IF FOUND THEN
    UPDATE schedule_slots SET is_booked = FALSE WHERE id = v_slot;
    RAISE NOTICE 'Запись отменена и слот освобождён.';
  END IF;
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
-- Name: idx_reviews_salon_created; Type: INDEX; Schema: smart_spa; Owner: postgres
--

CREATE INDEX idx_reviews_salon_created ON smart_spa.reviews USING btree (salon_id, created_at DESC);


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

\unrestrict T9aZownHAUEgUAUgaHfQq8p55vs7hcTmW8vHtmHWcSr8sN3UtNRfssY61ivG3UL

