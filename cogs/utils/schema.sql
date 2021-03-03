-- The MIT License (MIT)
--
-- Copyright (c) 2021 Mieszko Exchange

-- TODO: get mysql setup first lol

-- Currency data storage
-- TODO: maybe pull this directly from PaymentsDev.Currency instead?
CREATE TABLE `Currency` (
  `id` int(10) unsigned NOT NULL PRIMARY KEY AUTO_INCREMENT,
  `code` varchar(4) NOT NULL UNIQUE KEY,
  `precision` tinyint(3) unsigned NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Database error logging
CREATE TABLE `LoggedError` (
    `pk` int(10) NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `level` enum('CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG') NOT NULL,
    `module` tinytext NOT NULL,
    `function` tinytext NOT NULL,
    `filename` tinytext NOT NULL,
    `line` smallint unsigned NOT NULL,
    `message` varchar(1000) NOT NULL,
    `timestamp` datetime NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Discord <-> Bot connection
CREATE TABLE `User` (
    `discordId` bigint unsigned NOT NULL PRIMARY KEY,
    `createdAt` datetime NOT NULL,
    `locked` tinyint(1) unsigned NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- Addresses stored for convienence
CREATE TABLE `LinkedAddress` (
    `userId` bigint unsigned NOT NULL PRIMARY KEY,
    `currency` int(10) unsigned NOT NULL,
    `address` tinytext NOT NULL,
    `locked` tinyint(1) unsigned NOT NULL DEFAULT 0,
    KEY `currency` (`currency`),
    FOREIGN KEY (`userID`) REFERENCES `User` (`discordId`) ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (`currency`) REFERENCES `Currency` (`id`) ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Escrow stuff
CREATE TABLE `EscrowPayment` (
    `id` serial PRIMARY KEY,
    `currency` int(10) unsigned NOT NULL,
    `sender` bigint unsigned NOT NULL,
    `receiver` bigint unsigned NOT NULL,


    PRIMARY KEY (`sender`, `reciever`),
    KEY `currency` (`currency`),
    KEY `sender` (`sender`),
    KEY `receiver` (`receiver`),

    FOREIGN KEY (`curency`) REFERENCES `Currency` (`id`) ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (`sender`) REFERENCES `User` (`discordId`) ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (`receiver`) REFERENCES `User` (`discordId`) ON UPDATE CASCADE ON DELETE CASCADE,
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;