import React from 'react';
import { Link, generatePath } from 'react-router-dom';
import { isDefined } from '@togglecorp/fujs';

import NumberOutput from '#components/NumberOutput';
import routes from '#base/configs/routes';
import { formatTimeDuration } from '#utils/temporal';

import styles from './styles.css';

interface Props {
    member: {
        totalMappingProjects: number;
        totalSwipeTime: number;
        totalSwipes: number;
        username: string;
        userId: string;
        isActive: boolean;
    };
}

function MemberItem(props: Props) {
    const { member } = props;

    const path = generatePath(
        routes.userDashboard.path,
        { userId: member.userId },
    );

    return (
        <div className={styles.member}>
            <div className={styles.memberName}>
                <Link
                    className={styles.link}
                    to={path}
                >
                    {member.username}
                </Link>
                {!member.isActive && (
                    <div className={styles.inactive}>
                        No longer a member
                    </div>
                )}
            </div>
            <div className={styles.item}>
                <NumberOutput
                    value={member.totalSwipes}
                    normal
                />
            </div>
            <div className={styles.item}>
                <NumberOutput
                    value={member.totalMappingProjects}
                />
            </div>
            <div className={styles.item}>
                <div>
                    {isDefined(member.totalSwipeTime) ? formatTimeDuration(member.totalSwipeTime) : '-'}
                </div>
            </div>
        </div>
    );
}

export default MemberItem;
