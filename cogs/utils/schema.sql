-- The MIT License (MIT)
--
-- Copyright (c) 2021 Mieszko Exchange

-- Currency data storage
CREATE TABLE Currency (
  id int(10) unsigned NOT NULL AUTO_INCREMENT,
  code varchar(4) NOT NULL UNIQUE KEY,
  `precision` tinyint(3) unsigned NOT NULL,
  PRIMARY KEY (id)
  KEY (code),
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Database error logging
CREATE TABLE LoggedError (
    pk int(10) NOT NULL AUTO_INCREMENT,
    `level` enum('CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG') NOT NULL,
    module tinytext NOT NULL,
    function tinytext NOT NULL,
    filename tinytext NOT NULL,
    lineno smallint unsigned NOT NULL,
    message varchar(1000) NOT NULL,
    `timestamp` datetime NOT NULL,
    PRIMARY KEY (pk)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Discord <-> Bot connection
CREATE TABLE User (
    discordID bigint unsigned NOT NULL,
    createdAt datetime NOT NULL,
    locked tinyint(1) unsigned NOT NULL DEFAULT 0,
    PRIMARY KEY (discordID)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Addresses stored for convienence
CREATE TABLE LinkedAddress (
    userID bigint unsigned NOT NULL,
    currency int(10) unsigned NOT NULL,
    address varchar(256) NOT NULL,
    public tinyint(1) unsigned NOT NULL DEFAULT 1,
    PRIMARY KEY (userID, currency),
    KEY (address),
    FOREIGN KEY (userID) REFERENCES User (discordID) ON UPDATE CASCADE,
    FOREIGN KEY (currency) REFERENCES Currency (id) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Escrow stuff
CREATE TABLE EscrowPayment (
    id serial, -- necessary for EscrowEvent relation
    currency int(10) unsigned NOT NULL,
    sender bigint unsigned NOT NULL,
    receiver bigint unsigned NOT NULL,
    sourceAddress varchar(256) NOT NULL,
    destAddress varchar(256) NOT NULL,
    status enum('pending', 'paid', 'complete', 'failed') NOT NULL,
    amount decimal(24, 12) unsigned NOT NULL,
    startedAt timestamp NOT NULL,
    forMessage tinytext,
    lastActionAt timestamp,
    PRIMARY KEY (id),
    KEY(sender, receiver),
    KEY (sourceAddress, destAddress),
    KEY (currency),
    KEY (sender),
    KEY (receiver),
    FOREIGN KEY (currency) REFERENCES Currency (id) ON UPDATE CASCADE,
    FOREIGN KEY (sender) REFERENCES User (discordID) ON UPDATE CASCADE,
    FOREIGN KEY (receiver) REFERENCES User (discordID) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Escrow action details
CREATE TABLE EscrowEvent (
    paymentID serial,
    action enum('cancel', 'release', 'abort'),
    actioner enum('sender', 'receiver', 'moderator') NOT NULL,
    actionerID bigint unsigned NOT NULL,
    actionAt timestamp NOT NULL,
    actionMsg tinytext,
    PRIMARY KEY (paymentID),
    KEY (actioner),
    KEY (actionerID),
    FOREIGN KEY (paymentID) REFERENCES EscrowPayment (id) ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (actionerID) REFERENCES User (discordID) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
